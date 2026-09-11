# Copyright 2026 Google LLC. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Ray Data datasource for LeRobot Dataset **v3**

A LeRobot v3 dataset is a flat table of timestep samples.  Each row combines
low-dimensional data (state, action, etc.) from chunked parquet files with
decoded camera frames from chunked mp4 files.  Episode metadata ties them
together, recording which parquet chunk and which video file each episode
belongs to, and the seek timestamp (``from_timestamp``) where each episode
starts within its video file.

Output columns::

    index            int64    global 0-based row id
    episode_index    int64    which episode this row belongs to
    frame_index      int64    0-based position within the episode
    timestamp        float64  elapsed seconds within the episode
    <state/action>   float32  low-dimensional vectors from parquet
    <camera_key>     uint8    decoded HWC RGB frame for that camera
    task             str      natural-language task description

Partitioning
------------
+---------------+------------------+------------------------------------+
| Mode          | Tasks created    | Best for                           |
+===============+==================+====================================+
| ``episode``   | one per episode  | small local datasets; maximum      |
|               |                  | task count regardless of I/O cost  |
+---------------+------------------+------------------------------------+
| ``file_group``| one per unique   | **default**, balanced tasks with  |
| *(default)*   | video-file set   | each mp4 opened once per task      |
+---------------+------------------+------------------------------------+
| ``chain``     | one per connected| large cloud datasets where         |
|               | component of     | minimising total video-file opens  |
|               | file groups      | across workers matters most        |
+---------------+------------------+------------------------------------+
| ``sequential``| one (total)      | cloud datasets where peak memory   |
|               |                  | must be minimised over throughput  |
+---------------+------------------+------------------------------------+
| ``row_block`` | ceil(total / N)  | fixed-size blocks of N rows;       |
|               |                  | set via ``block_size`` argument    |
+---------------+------------------+------------------------------------+

Typical usage::

    import ray
    from tools.lerobot_datasource import LeRobotDatasource, read_lerobot, Partitioning

    ds = read_lerobot("/data/my_dataset")
    ds = read_lerobot("gs://bucket/dataset", partitioning=Partitioning.EPISODE)
    ds = read_lerobot("/data/my_dataset", partitioning=Partitioning.ROW_BLOCK, block_size=1024)

    # Multiple roots: rows from all datasets are interleaved; dataset_index identifies the source.
    ds = read_lerobot(["/data/ds1", "/data/ds2"])
    ds = read_lerobot(["gs://bucket/ds1", "gs://bucket/ds2"], partitioning=Partitioning.EPISODE)

    # Access metadata via the datasource directly:
    source = LeRobotDatasource("/data/my_dataset")
    print(source.meta.total_frames, source.meta.video_keys)
    ds = ray.data.read_datasource(source)
"""

import enum
import json
import logging
from pathlib import Path
from typing import Any, Iterator

import av
import fsspec
import numpy as np
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
import ray
from ray.data.block import BlockMetadata
from ray.data.context import DataContext
from ray.data.datasource import Datasource
from ray.data.datasource.datasource import ReadTask
from ray.data.extensions import ArrowVariableShapedTensorArray, ArrowVariableShapedTensorType

logger = logging.getLogger(__name__)

# Opt-in via env var LEROBOT_S3_ANON=1: force anonymous (unsigned) S3 reads. Used when
# the dataset lives in a public bucket that clusters may reach without credentials --
# signed reads can 403 there, unsigned always work. Set at import so it also takes effect
# inside Ray Data read workers (this module is shipped via runtime_env working_dir and
# re-imported there). All file opens in this module go through fsspec.core.url_to_fs,
# which honors this config.
import os as _os

if _os.environ.get("LEROBOT_S3_ANON", "").lower() in ("1", "true", "yes"):
    fsspec.config.conf.setdefault("s3", {})["anon"] = True

__all__ = [
    "LeRobotDatasource",
    "LeRobotDatasourceMetadata",
    "Partitioning",
    "read_lerobot",
]


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class Partitioning(enum.Enum):
    """How the dataset is partitioned into Ray Data read tasks.

    See the module-level "Partitioning" table for guidance.
    String aliases (e.g. ``"episode"``) are accepted wherever a member is expected.
    """

    EPISODE = "episode"
    FILE_GROUP = "file_group"
    CHAIN = "chain"
    SEQUENTIAL = "sequential"
    ROW_BLOCK = "row_block"


class LeRobotDatasourceMetadata:
    """Lightweight metadata container for a LeRobot v3 dataset.

    Eagerly loads ``meta/info.json``, ``meta/stats.json``,
    ``meta/episodes/**/*.parquet``, and ``meta/tasks.parquet`` from
    local or cloud storage.  All subsequent I/O (data parquet files,
    video files) is deferred to workers.

    ``fs`` is not stored on the instance.  The driver creates it locally
    during ``__init__`` and passes it to the fetch helpers.  Workers
    create their own connection from ``self.root`` using whatever
    credentials they have available (IAM role, Workload Identity,
    environment variables, etc.).

    Examples::

        meta = LeRobotDatasourceMetadata("/data/my_dataset")
        meta = LeRobotDatasourceMetadata("gs://bucket/my_dataset")
        print(meta.total_episodes, meta.video_keys)
    """

    def __init__(self, root: str | Path) -> None:
        """Load dataset metadata from *root* (local path or cloud URI).

        Args:
            root: Path or URI to the dataset root (local, ``gs://``, ``s3://``).

        Raises:
            FileNotFoundError: If ``meta/info.json`` or the episodes parquet
                files are missing.
            ValueError: If ``meta/info.json`` is missing required keys, the
                episode index is not 0-based and contiguous, or
                ``meta/tasks.parquet`` has no recognised task column.
        """
        self.root = str(root).rstrip("/")
        fs, self.fs_root = fsspec.core.url_to_fs(root)

        self.info = self._fetch_info(fs)
        self.video_keys: list[str] = [
            k for k, v in self.info["features"].items() if v.get("dtype") == "video"
        ]
        if self.video_keys and not self.info.get("video_path"):
            raise ValueError(
                f"{self.root!r}: dataset has video keys {self.video_keys} "
                "but meta/info.json has no 'video_path' template"
            )

        with fs.open(f"{self.fs_root}/meta/stats.json", "r") as f:
            self.stats: dict[str, dict] = json.load(f)

        self.episodes = self._fetch_episodes(fs)

        tasks_table = pq.read_table(fs.open(f"{self.fs_root}/meta/tasks.parquet", "rb"))
        if "task" in tasks_table.column_names:
            _task_col = "task"
        elif "__index_level_0__" in tasks_table.column_names:
            _task_col = "__index_level_0__"
        else:
            raise ValueError(
                f"{self.root!r}: meta/tasks.parquet has no recognised task column "
                f"(expected 'task' or '__index_level_0__'); found {tasks_table.column_names}"
            )
        self.tasks: dict[int, str] = dict(
            zip(
                tasks_table.column("task_index").to_pylist(),
                tasks_table.column(_task_col).to_pylist(),
            )
        )

        self.schema: pa.Schema = self._fetch_schema(fs)

    def _fetch_schema(self, fs: Any) -> pa.Schema:
        """Read Arrow schema from the first data parquet file; append video and task fields."""
        ep = self.episodes.slice(0, 1).to_pylist()[0]
        path = f"{self.fs_root}/{self.data_path_template.format(chunk_index=ep['data/chunk_index'], file_index=ep['data/file_index'])}"
        with fs.open(path, "rb") as f:
            pq_schema = pq.read_schema(f)
        fields = list(pq_schema)
        for vk in self.video_keys:
            fields.append(pa.field(vk, ArrowVariableShapedTensorType(pa.uint8(), ndim=3)))
        fields.append(pa.field("task", pa.string()))
        fields.append(pa.field("dataset_index", pa.int32()))
        return pa.schema(fields)

    def _fetch_info(self, fs: Any) -> dict:
        """Load and validate ``meta/info.json``."""
        info_path = f"{self.fs_root}/meta/info.json"
        if not fs.exists(info_path):
            raise FileNotFoundError(
                f"No LeRobot dataset found at {self.root!r}: meta/info.json is missing. "
                "Make sure the path points to the dataset root."
            )
        with fs.open(info_path, "r") as f:
            info = json.load(f)
        for required in (
            "total_frames",
            "total_episodes",
            "fps",
            "data_path",
            "features",
        ):
            if required not in info:
                raise ValueError(
                    f"{self.root!r}: meta/info.json is missing required key {required!r}"
                )
        return info

    def _fetch_episodes(self, fs: Any) -> pa.Table:
        """Load ``meta/episodes/**/*.parquet`` and append global index columns.

        Computes ``_global_from_index`` / ``_global_to_index`` from cumulative
        episode lengths rather than trusting ``dataset_from_index``, which some
        datasets store as per-file local offsets rather than global row numbers.
        """
        ep_files = sorted(fs.glob(f"{self.fs_root}/meta/episodes/**/*.parquet"))
        if not ep_files:
            raise FileNotFoundError(
                f"No episode parquet files found under {self.root!r}/meta/episodes/. "
                "The dataset may be incomplete or use an unsupported layout."
            )
        episodes = pa.concat_tables([pq.read_table(fs.open(f, "rb")) for f in ep_files])
        ep_indices = episodes.column("episode_index").to_pylist()
        if ep_indices != list(range(len(ep_indices))):
            raise ValueError(
                f"Episodes are not 0-indexed and contiguous: "
                f"first={ep_indices[0]}, last={ep_indices[-1]}, count={len(ep_indices)}"
            )
        lengths = episodes.column("length").to_pylist()
        global_from: list[int] = []
        running = 0
        for ln in lengths:
            global_from.append(running)
            running += ln
        global_to = global_from[1:] + [running]
        episodes = episodes.append_column(
            "_global_from_index", pa.array(global_from, type=pa.int64())
        ).append_column(
            "_global_to_index", pa.array(global_to, type=pa.int64())
        )
        return episodes

    @property
    def total_frames(self) -> int:
        """Total number of frames across all episodes."""
        return self.info["total_frames"]

    @property
    def total_episodes(self) -> int:
        """Total number of episodes in the dataset."""
        return self.info["total_episodes"]

    @property
    def estimated_row_size_bytes(self) -> int:
        """Estimated in-memory size of one fully-decoded frame row (bytes)."""
        features = self.info.get("features", {})
        total = 0
        for feat in features.values():
            if feat.get("dtype") == "video":
                shape = feat.get("shape")
                if shape:
                    total += int(np.prod(shape))
            else:
                shape = feat.get("shape", [1])
                try:
                    total += int(np.prod(shape)) * np.dtype(feat["dtype"]).itemsize
                except (TypeError, KeyError):
                    continue
        return total

    @property
    def video_path_template(self) -> str:
        """``video_path`` format string from ``meta/info.json``."""
        return self.info["video_path"]

    @property
    def data_path_template(self) -> str:
        """``data_path`` format string from ``meta/info.json``."""
        return self.info["data_path"]


class _ReadCancelled(Exception):
    """Ray cancelled this read task. Raised inside the reader, caught in _read.

    Distinct from the exhaustion RuntimeError _next_frame raises: a cancelled
    read stops mid-file by design, and reporting that as a truncated video would
    be wrong.
    """


class _CancelSafeFile:
    """File proxy that reports EOF instead of letting a cancellation reach PyAV.

    PyAV reads a file-like object through a C callback
    (``av.container.pyio.pyio_read_gil``). Ray cancels a read task by raising
    KeyboardInterrupt in the worker, and when that lands inside ``read()`` --
    called from within the callback -- the exception cannot propagate through
    the C frame: CPython prints "Exception ignored in ..." plus the full
    traceback and carries on. Returning empty bytes instead reads as
    end-of-file, so PyAV unwinds normally and ``cancelled`` tells the caller to
    stop streaming.
    """

    def __init__(self, fileobj):
        self._f = fileobj
        self.cancelled = False

    def read(self, *args, **kwargs):
        try:
            return self._f.read(*args, **kwargs)
        except KeyboardInterrupt:
            self.cancelled = True
            return b""

    def seek(self, *args, **kwargs):
        try:
            return self._f.seek(*args, **kwargs)
        except KeyboardInterrupt:
            self.cancelled = True
            return self._f.tell()

    def __getattr__(self, name):
        return getattr(self._f, name)


class LeRobotReadTask(ReadTask):
    """A Ray Data read task covering one or more contiguous row segments.

    Each segment is a ``(root_index, start, end)`` triple referencing a
    contiguous row range within one root of :class:`LeRobotDatasource`.
    A task may span multiple roots; segments are read independently.

    Constructed by :meth:`LeRobotDatasource.get_read_tasks`; not part of the
    public API.

    Args:
        segments:           ``(root_index, start, end)`` triples to read.
        metas_ref:          Ray object reference to the list of dataset metadata.
        rows_per_batch:     Maximum rows per yielded Arrow table.
        per_task_row_limit: Passed through to :class:`ReadTask`.
    """

    def __init__(
        self,
        segments: list[tuple[int, int, int]],
        metas_ref: "ray.ObjectRef",
        rows_per_batch: int,
        per_task_row_limit: int | None = None,
        action_chunk_size: int = 1,
    ) -> None:
        metas: list[LeRobotDatasourceMetadata] = ray.get(metas_ref)
        # Resolve paths now (no I/O, pure computation) so input_files is
        # populated in BlockMetadata and the result can be reused in _read.
        total_rows = 0
        size_bytes = 0
        all_input_files: list[str] = []
        resolved: list[tuple[int, int, int, Any]] = []
        for root_idx, start, end in segments:
            meta = metas[root_idx]
            paths = LeRobotReadTask._resolve_paths(meta, start, end)
            parquet_segs, video_paths = paths[0], paths[1]
            all_input_files.extend(parquet_segs)
            all_input_files.extend(p for ps in video_paths.values() for p in ps)
            total_rows += end - start
            size_bytes += (end - start) * meta.estimated_row_size_bytes
            resolved.append((root_idx, start, end, paths))

        schema = metas[segments[0][0]].schema
        block_metadata = BlockMetadata(
            num_rows=total_rows,
            size_bytes=size_bytes,
            input_files=all_input_files,
            exec_stats=None,
        )
        super().__init__(self._read, block_metadata, schema, per_task_row_limit)
        self._metas_ref = metas_ref
        self._segments_resolved = resolved
        self._rows_per_batch = rows_per_batch
        self._action_chunk_size = int(action_chunk_size)

    def _read(self) -> Iterator[pa.Table]:
        """Stream decoded rows as Arrow tables, iterating over all segments.

        Ray Data cancels still-running read tasks whenever the consumer stops
        early -- a ``limit()`` reaching its row count, or a training loop that
        breaks at ``max_train_steps``. Cancellation arrives as a KeyboardInterrupt
        raised in this worker, so a routine, expected teardown otherwise dumps a
        full traceback into the driver's output. Ending the generator quietly
        finishes the task just as fast, without the alarming output.
        """
        metas: list[LeRobotDatasourceMetadata] = ray.get(self._metas_ref)
        try:
            for root_idx, start, end, resolved_paths in self._segments_resolved:
                yield from self._read_segment(
                    metas[root_idx], start, end, root_idx, resolved_paths
                )
        except (_ReadCancelled, KeyboardInterrupt):
            return

    def _read_segment(
        self,
        meta: "LeRobotDatasourceMetadata",
        start: int,
        end: int,
        dataset_index: int,
        resolved_paths: tuple,
    ) -> Iterator[pa.Table]:
        """Stream decoded rows for one ``[start, end)`` range within a single root.

        Data flow
        ---------
        ::

            _frame_stream per camera
              seek first mp4 to video_start_ts
              yield (frame, half_dt)   where half_dt = 0.5 / fps

            ┌─ for parquet_seg ────────────────────────────────────────┐
            │  pq.read_table(filters=[start <= index < end])           │
            │                                                           │
            │  ┌─ for row ─────────────────────────────────────────┐   │
            │  │  ep_idx, row_ts <- episode_index, timestamp cols  │   │
            │  │                                                    │   │
            │  │  for cam in video_keys:                           │   │
            │  │    target_ts = ep_from_ts[cam][ep_idx] + row_ts   │   │
            │  │    while frame.time < target_ts - half_dt:        │   │
            │  │      advance frame iter (_next_frame)              │   │
            │  │    append frame.to_ndarray("rgb24") to buffer      │   │
            │  │                                                    │   │
            │  │  append pq row + task string to buffers            │   │
            │  │  if len(buffer) >= rows_per_batch:                 │   │
            │  │    yield _build_batch()  ->  Arrow table           │   │
            │  └───────────────────────────────────────────────────┘   │
            └──────────────────────────────────────────────────────────┘

            yield remaining buffered rows as a final batch

        """
        parquet_segs, video_paths, video_start_ts, ep_from_ts = resolved_paths

        fs, _ = fsspec.core.url_to_fs(meta.root)
        is_local = fs.protocol == "file" if isinstance(fs.protocol, str) else "file" in fs.protocol

        pq_buffer: list[pa.Table] = []
        frame_buffers: dict[str, list[np.ndarray]] = {k: [] for k in meta.video_keys}
        task_list: list[str] = []

        frame_iters = {
            k: self._frame_stream(fs, is_local, video_paths[k], video_start_ts[k])
            for k in meta.video_keys
        }
        cur: dict[str, Any] = {k: None for k in meta.video_keys}

        try:
            filters = [("index", ">=", start), ("index", "<", end)]

            for path in parquet_segs:
                with fs.open(path, "rb") as f:
                    pq_table = pq.read_table(f, filters=filters)

                # read_table materializes the whole filtered segment, so the
                # future actions a chunk needs are already in memory here. Doing
                # this per segment (rather than per emitted batch) means chunks
                # never need rows that have not been read yet.
                if self._action_chunk_size > 1:
                    pq_table = self._chunk_action_column(
                        pq_table, self._action_chunk_size,
                    )

                task_idx_col = pq_table.column("task_index")
                timestamp_col = pq_table.column("timestamp")
                ep_idx_col   = pq_table.column("episode_index")
                seg_start = 0

                for row_idx in range(pq_table.num_rows):
                    ep_idx = ep_idx_col[row_idx].as_py()
                    row_ts = timestamp_col[row_idx].as_py()

                    for k in meta.video_keys:
                        target_ts = ep_from_ts[k][ep_idx] + row_ts
                        if cur[k] is None:
                            cur[k] = self._next_frame(frame_iters, start, k, row_idx, ep_idx)
                        while cur[k][0].time is None or cur[k][0].time < target_ts - cur[k][1]:
                            cur[k] = self._next_frame(frame_iters, start, k, row_idx, ep_idx)
                        frame_buffers[k].append(cur[k][0].to_ndarray(format="rgb24"))

                    task_list.append(meta.tasks[task_idx_col[row_idx].as_py()])

                    if len(task_list) >= self._rows_per_batch:
                        pq_buffer.append(pq_table.slice(seg_start, row_idx + 1 - seg_start))
                        yield self._build_batch(meta.video_keys, pq_buffer, frame_buffers, task_list, dataset_index)
                        pq_buffer = []
                        frame_buffers = {k: [] for k in meta.video_keys}
                        task_list = []
                        seg_start = row_idx + 1

                if seg_start < pq_table.num_rows:
                    pq_buffer.append(pq_table.slice(seg_start))

        finally:
            for it in frame_iters.values():
                it.close()

        if pq_buffer:
            yield self._build_batch(meta.video_keys, pq_buffer, frame_buffers, task_list, dataset_index)

    @staticmethod
    def _resolve_paths(
        meta: "LeRobotDatasourceMetadata",
        start: int,
        end: int,
    ) -> tuple[
        list[str],
        dict[str, list[str]],
        dict[str, float],
        dict[str, dict[int, float]],
    ]:
        """Resolve all file paths needed to read rows ``[start, end)``.

        Returns ``(parquet_segs, video_paths, video_start_ts, ep_from_ts)``.
        No I/O, pure computation from the episodes table and path templates.
        """
        start_ep, end_ep = LeRobotReadTask._episodes_for_row_range(meta.episodes, start, end)
        ep_slice = meta.episodes.slice(start_ep, end_ep - start_ep)

        pq_chunks = ep_slice.column("data/chunk_index").combine_chunks()
        pq_files  = ep_slice.column("data/file_index").combine_chunks()
        pq_new    = LeRobotReadTask._segment_boundaries(pq_chunks, pq_files)
        parquet_segs: list[str] = [
            f"{meta.fs_root}/{meta.data_path_template.format(chunk_index=c, file_index=f)}"
            for c, f in zip(
                pc.filter(pq_chunks, pq_new).to_pylist(),  # type: ignore[attr-defined]
                pc.filter(pq_files,  pq_new).to_pylist(),  # type: ignore[attr-defined]
            )
        ]

        video_paths: dict[str, list[str]] = {}
        video_start_ts: dict[str, float] = {}
        ep_from_ts: dict[str, dict[int, float]] = {}
        if meta.video_keys:
            video_path_template = meta.video_path_template
            ep_indices = ep_slice.column("episode_index").to_pylist()
            for k in meta.video_keys:
                from_ts_vals = ep_slice.column(f"videos/{k}/from_timestamp").to_pylist()
                ep_from_ts[k] = dict(zip(ep_indices, from_ts_vals))
                chunks = ep_slice.column(f"videos/{k}/chunk_index").combine_chunks()
                files  = ep_slice.column(f"videos/{k}/file_index").combine_chunks()
                is_new = LeRobotReadTask._segment_boundaries(chunks, files)
                video_paths[k] = [
                    f"{meta.fs_root}/{video_path_template.format(video_key=k, chunk_index=c, file_index=f)}"
                    for c, f in zip(
                        pc.filter(chunks, is_new).to_pylist(),  # type: ignore[attr-defined]
                        pc.filter(files,  is_new).to_pylist(),  # type: ignore[attr-defined]
                    )
                ]
                video_start_ts[k] = from_ts_vals[0] if from_ts_vals else 0.0

        return parquet_segs, video_paths, video_start_ts, ep_from_ts

    @staticmethod
    def _episodes_for_row_range(
        episodes: pa.Table,
        start_row: int,
        end_row: int,
    ) -> tuple[int, int]:
        """Return the half-open ``(start_ep, end_ep)`` range covering ``[start_row, end_row)``."""
        from_idx = episodes.column("_global_from_index")
        to_idx = episodes.column("_global_to_index")
        mask = pc.and_(  # type: ignore[attr-defined]
            pc.less(from_idx, end_row),  # type: ignore[attr-defined]
            pc.greater(to_idx, start_row),  # type: ignore[attr-defined]
        )
        indices = pc.filter(  # type: ignore[attr-defined]
            episodes.column("episode_index"), mask
        ).to_pylist()
        if not indices:
            raise ValueError(
                f"No episodes overlap the row range [{start_row}, {end_row}). "
                f"Dataset has {episodes.column('_global_to_index')[-1].as_py()} total frames "
                f"across {len(episodes)} episodes."
            )
        return (indices[0], indices[-1] + 1)

    @staticmethod
    def _segment_boundaries(col_a: pa.ChunkedArray, col_b: pa.ChunkedArray) -> pa.BooleanArray:
        """Boolean mask: True at index 0 and wherever the ``(col_a, col_b)`` pair changes."""
        n = len(col_a)
        if n == 0:
            return pa.array([], type=pa.bool_())
        return pa.concat_arrays(  # type: ignore[return-value]
            [
                pa.array([True]),
                pc.or_(  # type: ignore[attr-defined]
                    pc.not_equal(col_a.slice(1), col_a.slice(0, n - 1)),  # type: ignore[attr-defined]
                    pc.not_equal(col_b.slice(1), col_b.slice(0, n - 1)),  # type: ignore[attr-defined]
                ),
            ]
        )

    @staticmethod
    def _frame_stream(fs: Any, is_local: bool, fs_paths: list[str], start_ts: float):
        """Yield ``(frame, half_frame)`` across all video files for one camera.

        Mirrors lerobot's ``video_backend="pyav"`` strategy: seek the first file
        to ``start_ts`` (the nearest preceding keyframe), then walk frames
        forward.  Subsequent files start at their beginning so no seek is needed.
        ``av.open()`` accepts file-like objects so local, GCS, and S3 paths all
        use the same code path with no GPU or PyTorch dependency.
        """
        for i, path in enumerate(fs_paths):
            # Remote reads go through a Python file object that PyAV calls from
            # C, which is where a cancellation would otherwise escape as an
            # uncatchable "Exception ignored in: 'av.container.pyio.pyio_read_gil'"
            # traceback -- see _CancelSafeFile.
            handle = None if is_local else _CancelSafeFile(fs.open(path, "rb"))
            container = av.open(path) if is_local else av.open(handle)
            try:
                stream = container.streams.video[0]
                if stream.time_base is None or stream.average_rate is None:
                    raise ValueError(
                        f"Video stream in {path!r} has no time_base or average_rate; "
                        "the file may be corrupt or encoded without timing metadata."
                    )
                if i == 0 and start_ts > 0:
                    container.seek(int(start_ts / stream.time_base), stream=stream)
                half_frame = 0.5 / float(stream.average_rate)
                for packet in container.demux(video=0):
                    try:
                        for frame in packet.decode():
                            yield frame, half_frame
                    except av.InvalidDataError:
                        # Corrupted packets can appear just after a seek; skip.
                        continue
                    if handle is not None and handle.cancelled:
                        raise _ReadCancelled
            except KeyboardInterrupt:
                # Ray cancelled this read task (consumer stopped early).
                raise _ReadCancelled from None
            except av.FFmpegError:
                # The EOF _CancelSafeFile reports on cancellation can surface
                # here as truncated input. Anything else is a real decode error.
                if handle is not None and handle.cancelled:
                    raise _ReadCancelled from None
                raise
            finally:
                container.close()

    @staticmethod
    def _build_batch(
        video_keys: list[str],
        pq_buffer: list[pa.Table],
        frame_buffers: dict[str, list[np.ndarray]],
        task_list: list[str],
        dataset_index: int,
    ) -> pa.Table:
        """Assemble one Arrow batch from buffered parquet rows, decoded frames, and tasks."""
        table = pa.concat_tables(pq_buffer)
        columns: dict[str, Any] = {
            table.schema.field(i).name: table.column(i)
            for i in range(table.num_columns)
        }
        for k in video_keys:
            columns[k] = ArrowVariableShapedTensorArray.from_numpy(frame_buffers[k])
        columns["task"] = pa.array(task_list, type=pa.string())
        columns["dataset_index"] = pa.array([dataset_index] * len(task_list), type=pa.int32())
        return pa.table(columns)

    @staticmethod
    def _chunk_action_column(pq_table: pa.Table, chunk_size: int) -> pa.Table:
        """Replace per-frame ``action`` with an ``(chunk_size, action_dim)`` chunk.

        PI0.5 is an action-*chunking* policy: its config sets
        ``chunk_size == n_action_steps == 50``, and its flow-matching loss
        compares ``v_t`` of shape ``[B, chunk, action_dim]`` against ``u_t``
        derived from the target action. Handing it one action per frame makes
        ``u_t`` ``[B, action_dim]`` while ``v_t`` stays ``[B, 1, action_dim]``, and
        ``F.mse_loss`` silently *broadcasts* rather than raising::

            UserWarning: Using a target size (torch.Size([1, 1, 32])) that is
            different to the input size (torch.Size([1, 32])). This will likely
            lead to incorrect results due to broadcasting.

        so the model regresses against a spurious axis and never learns chunks.

        Chunks are clipped to the episode: rows are contiguous and ordered within
        a segment, so episode extents come from ``episode_index`` runs. Past the
        end of an episode the final real action repeats (the same padding
        ``LeRobotDataset`` produces via ``delta_timestamps``), and a companion
        ``action_is_pad`` column marks which timesteps are padding so a caller can
        mask the loss. Nothing here consumes ``action_is_pad`` yet -- PI0.5's
        forward does not accept it, so the training loop drops it before the
        forward pass.
        """
        actions = np.asarray(
            pq_table.column("action").to_pylist(), dtype=np.float32,
        )
        if actions.ndim != 2:
            raise ValueError(
                f"expected a 2-D (rows, action_dim) action column, got "
                f"shape {actions.shape}; is it already chunked?"
            )
        episodes = np.asarray(pq_table.column("episode_index").to_pylist())
        n_rows = actions.shape[0]

        # exclusive end index of the episode each row belongs to
        run_starts = np.flatnonzero(
            np.concatenate(([True], episodes[1:] != episodes[:-1]))
        )
        run_ends = np.concatenate((run_starts[1:], [n_rows]))
        row_run = np.searchsorted(run_starts, np.arange(n_rows), side="right") - 1
        last_in_episode = (run_ends[row_run] - 1)[:, None]

        wanted = np.arange(n_rows)[:, None] + np.arange(chunk_size)[None, :]
        is_pad = wanted > last_in_episode
        chunks = actions[np.minimum(wanted, last_in_episode)]

        columns: dict[str, Any] = {
            pq_table.schema.field(i).name: pq_table.column(i)
            for i in range(pq_table.num_columns)
        }
        columns["action"] = ArrowVariableShapedTensorArray.from_numpy(list(chunks))
        columns["action_is_pad"] = ArrowVariableShapedTensorArray.from_numpy(list(is_pad))
        return pa.table(columns)

    @staticmethod
    def _next_frame(
        frame_iters: dict[str, Any],
        start: int,
        cam_key: str,
        row_idx: int,
        ep_idx: int,
    ) -> Any:
        """Advance one camera's iterator; raise ``RuntimeError`` with context on exhaustion."""
        try:
            return next(frame_iters[cam_key])
        except StopIteration:
            raise RuntimeError(
                f"Video stream for camera {cam_key!r} exhausted at"
                f" row {start + row_idx} (episode {ep_idx})."
                " The video file may be truncated."
            ) from None


class LeRobotDatasource(Datasource):
    """Ray Data ``Datasource`` for LeRobot v3 datasets.

    ``__init__`` does two things: loads dataset metadata into ``self.meta``
    and validates and stores the chosen *partitioning*.  No data files are
    opened and no row ranges are computed yet.

    When Ray calls :meth:`get_read_tasks`, the dataset is sliced into
    contiguous ``(start, end)`` row ranges according to *partitioning*,
    the ranges are grouped to respect the requested *parallelism*, and one
    :class:`LeRobotReadTask` is created per group.  Each task receives the
    full dataset metadata and its ``(start, end)`` span; file path resolution
    and all I/O happen on the worker at read time.

    Use :func:`read_lerobot` for typical use.  Construct this class directly
    when you need to inspect ``source.meta`` before reading, or when passing
    Ray Data execution options such as ``override_num_blocks`` or
    ``ray_remote_args`` to ``ray.data.read_datasource``.

    Attributes:
        meta: Dataset metadata loaded from *root* at construction time.

    Example::

        import ray
        from tools.lerobot_datasource import LeRobotDatasource, Partitioning

        source = LeRobotDatasource(root="/data/my_dataset")
        print(source.meta.total_frames, source.meta.video_keys)
        ds = ray.data.read_datasource(source)

        # Fixed 1024-row blocks, reading from GCS.
        ds = ray.data.read_datasource(LeRobotDatasource(
            root="gs://bucket/dataset",
            partitioning=Partitioning.ROW_BLOCK,
            block_size=1024,
        ))
    """

    def __init__(
        self,
        root: str | Path | list[str | Path],
        partitioning: Partitioning | str = Partitioning.FILE_GROUP,
        action_chunk_size: int = 1,
        **kwargs: Any,
    ):
        """
        Args:
            root: Path or URI to the dataset root (local, ``gs://``, ``s3://``),
                or a list of such paths to read multiple datasets as one.
                All roots must share the same ``video_keys``, ``fps``, and
                non-video feature names.
            partitioning: How to divide the dataset into read tasks.
                Accepts a :class:`Partitioning` member or its string value.
                Defaults to ``FILE_GROUP``.
            **kwargs: Forwarded to the partitioning helper at read time.
                ``ROW_BLOCK`` requires ``block_size``; other modes take none.

        Raises:
            ValueError: If *partitioning* is not recognised, if
                ``block_size`` is omitted for ``ROW_BLOCK`` mode, or if
                roots have incompatible schemas.
        """
        super().__init__()

        roots = [root] if isinstance(root, (str, Path)) else list(root)
        self.metas = [LeRobotDatasourceMetadata(r) for r in roots]

        if len(self.metas) > 1:
            ref = self.metas[0]
            for m in self.metas[1:]:
                if sorted(m.video_keys) != sorted(ref.video_keys):
                    raise ValueError(
                        f"video_keys mismatch: {ref.root!r} has {ref.video_keys} "
                        f"but {m.root!r} has {m.video_keys}"
                    )
                if m.info["fps"] != ref.info["fps"]:
                    raise ValueError(
                        f"fps mismatch: {ref.root!r} has {ref.info['fps']} "
                        f"but {m.root!r} has {m.info['fps']}"
                    )
                ref_feats = {
                    k for k, v in ref.info["features"].items()
                    if v.get("dtype") not in ("video",) and k != "task"
                }
                m_feats = {
                    k for k, v in m.info["features"].items()
                    if v.get("dtype") not in ("video",) and k != "task"
                }
                if ref_feats != m_feats:
                    raise ValueError(
                        f"Feature mismatch: {ref.root!r} has {sorted(ref_feats)} "
                        f"but {m.root!r} has {sorted(m_feats)}"
                    )

        if isinstance(partitioning, Partitioning):
            partitioning = partitioning.value

        _valid_modes = ("sequential", "episode", "file_group", "chain", "row_block")
        if partitioning not in _valid_modes:
            raise ValueError(
                f"Unknown partitioning {partitioning!r}. "
                f"Choose from: {', '.join(_valid_modes)}"
            )

        self._partitioning: str = partitioning
        self._slice_kwargs: dict[str, Any] = kwargs
        # 1 keeps the historical behaviour (one action per row). Set this to the
        # policy's chunk_size when training an action-chunking policy such as
        # PI0.5 (chunk_size=50) -- see _chunk_action_column for why feeding a
        # single action makes the flow-matching loss broadcast instead of match.
        self._action_chunk_size = int(action_chunk_size)
        if self._action_chunk_size < 1:
            raise ValueError(
                f"action_chunk_size must be >= 1, got {action_chunk_size}"
            )

        logger.info(
            "LeRobotDatasource ready: %d roots, %d total frames, %d cameras %s, mode=%r",
            len(self.metas),
            sum(m.total_frames for m in self.metas),
            len(self.meta.video_keys),
            self.meta.video_keys,
            partitioning,
        )

    @property
    def meta(self) -> LeRobotDatasourceMetadata:
        """Metadata for the first root; use ``self.metas`` for all roots."""
        return self.metas[0]

    # ------------------------------------------------------------------
    # Slicing helpers, called from get_read_tasks to produce row ranges
    # ------------------------------------------------------------------

    @staticmethod
    def _slices_sequential(ds_meta: LeRobotDatasourceMetadata) -> list[tuple[int, int]]:
        """Single slice spanning all rows: one task total, minimal peak memory."""
        return [(0, ds_meta.total_frames)]

    @staticmethod
    def _slices_by_episode(ds_meta: LeRobotDatasourceMetadata) -> list[tuple[int, int]]:
        """One slice per episode: maximum task count; same mp4 may be opened by multiple tasks."""
        from_indices = ds_meta.episodes.column("_global_from_index").to_pylist()
        to_indices = ds_meta.episodes.column("_global_to_index").to_pylist()
        return list(zip(from_indices, to_indices))

    @staticmethod
    def _slices_by_file_group(ds_meta: LeRobotDatasourceMetadata) -> list[tuple[int, int]]:
        """One slice per unique set of video files (default).

        Episodes sharing the same mp4 file for every camera are merged into one
        slice.  Episodes must be contiguous within each file group; raises
        ``ValueError`` if not (use ``CHAIN`` or ``EPISODE`` mode instead).
        """
        eps = ds_meta.episodes

        key_columns: list[list[int]] = []
        for vk in ds_meta.video_keys:
            key_columns.append(eps.column(f"videos/{vk}/chunk_index").to_pylist())
            key_columns.append(eps.column(f"videos/{vk}/file_index").to_pylist())

        from_indices = eps.column("_global_from_index").to_pylist()
        to_indices = eps.column("_global_to_index").to_pylist()

        ranges: dict[tuple[int, ...], tuple[int, int]] = {}
        for i in range(len(eps)):
            key = tuple(col[i] for col in key_columns)
            from_idx, to_idx = from_indices[i], to_indices[i]
            if key in ranges:
                prev_from, prev_to = ranges[key]
                if from_idx != prev_to:
                    raise ValueError(
                        f"Non-contiguous episodes share video-file group key {key!r}: "
                        f"existing span ends at row {prev_to} but the next episode "
                        f"(index {i}) starts at row {from_idx}. "
                        "Use CHAIN or EPISODE partitioning for datasets with "
                        "non-standard episode layouts."
                    )
                ranges[key] = (prev_from, to_idx)
            else:
                ranges[key] = (from_idx, to_idx)

        return list(ranges.values())

    @staticmethod
    def _slices_by_chain(ds_meta: LeRobotDatasourceMetadata) -> list[tuple[int, int]]:
        """One slice per connected component of episodes sharing any video file.

        Union-find over episodes; two episodes are in the same component when
        they share an mp4 for at least one camera.  Minimises total video-file
        opens at the cost of fewer, larger tasks.
        """
        eps = ds_meta.episodes
        n = len(eps)

        parent = list(range(n))
        rank = [0] * n

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        def union(a: int, b: int) -> None:
            ra, rb = find(a), find(b)
            if ra == rb:
                return
            if rank[ra] < rank[rb]:
                ra, rb = rb, ra
            parent[rb] = ra
            if rank[ra] == rank[rb]:
                rank[ra] += 1

        video_file_to_episode: dict[tuple[str, int, int], int] = {}
        for vid_key in ds_meta.video_keys:
            vid_chunks = eps.column(f"videos/{vid_key}/chunk_index").to_pylist()
            vid_files = eps.column(f"videos/{vid_key}/file_index").to_pylist()
            for ep_idx in range(n):
                file_key = (vid_key, vid_chunks[ep_idx], vid_files[ep_idx])
                if file_key in video_file_to_episode:
                    union(ep_idx, video_file_to_episode[file_key])
                else:
                    video_file_to_episode[file_key] = ep_idx

        from_indices = eps.column("_global_from_index").to_pylist()
        to_indices = eps.column("_global_to_index").to_pylist()

        component_ranges: dict[int, tuple[int, int]] = {}
        for ep_idx in range(n):
            root = find(ep_idx)
            from_idx, to_idx = from_indices[ep_idx], to_indices[ep_idx]
            if root in component_ranges:
                prev_from, prev_to = component_ranges[root]
                component_ranges[root] = (min(prev_from, from_idx), max(prev_to, to_idx))
            else:
                component_ranges[root] = (from_idx, to_idx)

        return sorted(component_ranges.values())

    @staticmethod
    def _slices_by_row_block(
        ds_meta: LeRobotDatasourceMetadata, block_size: int | None = None
    ) -> list[tuple[int, int]]:
        """Fixed-size blocks of ``block_size`` rows; boundaries may split episodes."""
        if block_size is None:
            raise ValueError("block_size is required when partitioning is 'row_block'")
        total = ds_meta.total_frames
        return [(i, min(i + block_size, total)) for i in range(0, total, block_size)]

    def _slice(self) -> list[tuple[int, int, int]]:
        """Return ``(root_index, start, end)`` triples for all roots, sorted."""
        slice_fns = {
            "sequential": self._slices_sequential,
            "episode": self._slices_by_episode,
            "file_group": self._slices_by_file_group,
            "chain": self._slices_by_chain,
            "row_block": self._slices_by_row_block,
        }
        all_ranges: list[tuple[int, int, int]] = []
        for root_idx, meta in enumerate(self.metas):
            ranges = sorted(slice_fns[self._partitioning](meta, **self._slice_kwargs))
            for i in range(1, len(ranges)):
                if ranges[i - 1][1] != ranges[i][0]:
                    raise ValueError(
                        f"Non-contiguous slices in root {root_idx} ({meta.root!r}): "
                        f"slice {i - 1} ends at row {ranges[i - 1][1]} "
                        f"but slice {i} starts at row {ranges[i][0]}."
                    )
            all_ranges.extend((root_idx, s, e) for s, e in ranges)
        return all_ranges

    def _rows_per_batch(self, data_context: DataContext | None) -> int:
        """Derive rows-per-batch from the Ray DataContext block-size target."""
        try:
            ctx = data_context or DataContext.get_current()
            max_block_bytes = ctx.target_max_block_size or 128 * 1024 * 1024
        except (AttributeError, RuntimeError):
            max_block_bytes = 128 * 1024 * 1024
        row_size_bytes = self.meta.estimated_row_size_bytes or 1
        return max(1, max_block_bytes // row_size_bytes)

    # ------------------------------------------------------------------
    # Ray Data API
    # ------------------------------------------------------------------

    def estimate_inmemory_data_size(self) -> int | None:
        """Hint for Ray Data's memory-aware scheduling."""
        return sum(m.total_frames * m.estimated_row_size_bytes for m in self.metas) or None

    def plan(self, parallelism: int = 0) -> list[dict]:
        """Return the read plan as a list of task descriptors, with no I/O and no Ray objects.

        Each entry describes one logical read task::

            {
                "task":         int,           # 0-based task index
                "start":        int,           # first global row (inclusive)
                "end":          int,           # last global row (exclusive)
                "num_rows":     int,
                "size_bytes":   int,           # estimated
                "parquet_files": list[str],
                "video_files":  dict[str, list[str]],  # keyed by video_key
            }

        Args:
            parallelism: Maximum number of tasks (same semantics as
                :meth:`get_read_tasks`).  ``0`` or negative means one task per
                natural slice (no merging).
        """
        row_ranges = self._slice()

        if parallelism > 0 and len(row_ranges) > parallelism:
            n = len(row_ranges)
            base, remainder = divmod(n, parallelism)
            groups: list[list[tuple[int, int, int]]] = []
            i = 0
            for g in range(parallelism):
                chunk_size = base + (1 if g < remainder else 0)
                groups.append(row_ranges[i : i + chunk_size])
                i += chunk_size
        else:
            groups = [[r] for r in row_ranges]

        result = []
        for idx, group in enumerate(groups):
            segments = LeRobotDatasource._merge_segments(group)
            num_rows = sum(e - s for _, s, e in segments)
            size_bytes = sum(
                (e - s) * self.metas[ri].estimated_row_size_bytes
                for ri, s, e in segments
            )
            result.append(
                {
                    "task": idx,
                    "segments": segments,
                    "num_rows": num_rows,
                    "size_bytes": size_bytes,
                }
            )
        return result

    @staticmethod
    def _merge_segments(
        group: list[tuple[int, int, int]],
    ) -> list[tuple[int, int, int]]:
        """Collapse adjacent same-root consecutive triples into wider segments."""
        if not group:
            return []
        segments: list[tuple[int, int, int]] = []
        prev_ri, prev_s, prev_e = group[0]
        for ri, s, e in group[1:]:
            if ri == prev_ri and s == prev_e:
                prev_e = e
            else:
                segments.append((prev_ri, prev_s, prev_e))
                prev_ri, prev_s, prev_e = ri, s, e
        segments.append((prev_ri, prev_s, prev_e))
        return segments

    def get_read_tasks(
        self,
        parallelism: int,
        per_task_row_limit: int | None = None,
        data_context: DataContext | None = None,
    ) -> list[ReadTask]:
        """Slice the dataset, group ranges into tasks, and return :class:`LeRobotReadTask` objects.

        Steps:

        1. **Slice**: call the appropriate ``_slices_*`` helper (chosen by
           *partitioning* at construction) to get per-root ``(root_idx, start, end)``
           triples; slicers themselves are unchanged and operate per root.
        2. **Group**: if there are more ranges than *parallelism* allows,
           merge consecutive triples so groups differ in size by at most one.
        3. **Wrap**: create one :class:`LeRobotReadTask` per group.  Each task
           receives its segment list and a shared ``ray.ObjectRef`` to the full
           metadata list; file path resolution and all I/O happen on the worker.
        """
        task_plan = self.plan(parallelism)

        logger.info(
            "%d tasks, %d total frames, %d roots, %d cameras",
            len(task_plan),
            sum(m.total_frames for m in self.metas),
            len(self.metas),
            len(self.meta.video_keys),
        )

        metas_ref = ray.put(self.metas)
        rows_per_batch = self._rows_per_batch(data_context)
        return [
            LeRobotReadTask(
                segments=entry["segments"],
                metas_ref=metas_ref,
                rows_per_batch=rows_per_batch,
                per_task_row_limit=per_task_row_limit,
                action_chunk_size=self._action_chunk_size,
            )
            for entry in task_plan
        ]


def read_lerobot(
    root: str | Path | list[str | Path],
    partitioning: Partitioning | str = Partitioning.FILE_GROUP,
    **kwargs: Any,
) -> "ray.data.Dataset":
    """Read one or more LeRobot datasets as a single Ray Data ``Dataset``.

    Convenience wrapper around ``ray.data.read_datasource(LeRobotDatasource(...))``.
    Video frames are decoded with PyAV and are pixel-identical to lerobot's
    ``video_backend="pyav"`` output.

    Extra keyword arguments are forwarded to :class:`LeRobotDatasource`.
    ``block_size`` is required when *partitioning* is ``ROW_BLOCK``.
    For Ray Data execution options (e.g. ``override_num_blocks``,
    ``ray_remote_args``) or access to the dataset metadata, construct
    :class:`LeRobotDatasource` directly and pass it to
    ``ray.data.read_datasource``; the metadata is available via ``source.meta``.

    Args:
        root: Path or URI to the dataset root (local, ``gs://``, ``s3://``),
            or a list of such paths.  All roots must have the same ``video_keys``,
            ``fps``, and non-video feature names.  Each output row includes a
            ``dataset_index`` (int32) column indicating which root it came from.
            ``episode_index`` and ``index`` retain per-root local values.
        partitioning: How to partition the dataset into read tasks.
            See :class:`Partitioning` for options; defaults to ``FILE_GROUP``.
        **kwargs: Forwarded to :class:`LeRobotDatasource` as slicer kwargs.

    Returns:
        A Ray Data ``Dataset`` of fully-decoded frames with columns listed in
        the module docstring, plus ``dataset_index``.

    Example::

        import ray
        from tools.lerobot_datasource import read_lerobot, Partitioning

        ds = read_lerobot("/data/my_dataset")
        ds = read_lerobot("gs://bucket/dataset", partitioning=Partitioning.EPISODE)
        ds = read_lerobot("/data/my_dataset", partitioning=Partitioning.ROW_BLOCK, block_size=1024)
        ds = read_lerobot(["/data/ds1", "/data/ds2"])
    """
    return ray.data.read_datasource(
        LeRobotDatasource(root=root, partitioning=partitioning, **kwargs)
    )
