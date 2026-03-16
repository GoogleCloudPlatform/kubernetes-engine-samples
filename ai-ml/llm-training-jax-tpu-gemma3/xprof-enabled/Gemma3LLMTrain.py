# Copyright 2026 Google LLC
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

import grain.python as pygrain
import jax
import jax.numpy as jnp
import optax
import pandas as pd
import time
import argparse
import equinox as eqx
from dataclasses import dataclass
from functools import partial
from gemma import gm
from flax.training import train_state
from jax.sharding import Mesh, PartitionSpec, NamedSharding
import logging

jax.distributed.initialize()
print("Global device count:", jax.device_count())
print("jax version:", jax.__version__)
logging.getLogger("jax").setLevel(logging.NOTSET)
jax.profiler.start_server(9002)

tokenizer = gm.text.Gemma3Tokenizer()
num_epochs = 1
learning_rate = 2e-5

@dataclass
class TextDataset:
    data: list
    maxlen: int
    tokenizer: gm.text.Gemma3Tokenizer

    def __len__(self):
        return len(self.data)

    def __getitem__(self, idx: int):
        encoding = self.tokenizer.encode(self.data[idx])[:self.maxlen]  # Tokenize and truncate
        return encoding + [0] * (self.maxlen - len(encoding))  # Pad to maxlen

def load_and_preprocess_data(file_path, batch_size, maxlen, datacount, tokenizer):

    with open(file_path, 'r') as f:
      text = f.read()

    stories = text.split('<|endoftext|>')
    stories = [story for story in stories if story.strip()][:datacount]
    df = pd.DataFrame({'text': stories})
    data = df['text'].dropna().tolist()
    dataset = TextDataset(data, maxlen, tokenizer)

    sampler = pygrain.IndexSampler(
        len(dataset),
        shuffle=False,
        seed=42,
        shard_options=pygrain.NoSharding(),
        num_epochs=num_epochs,
    )

    dataloader = pygrain.DataLoader(
        data_source=dataset,
        sampler=sampler,
        operations=[pygrain.Batch(batch_size=batch_size, drop_remainder=True)],
    )

    return dataloader

def generate_text(model, params, tokenizer, prompt):
    sampler = gm.text.Sampler(
        model=model,
        params=params,
        tokenizer=tokenizer,
    )
    print("Generating response for: " + prompt)
    out = sampler.sample(prompt, max_new_tokens=32)
    print("Reponse: \n" + out + "\n")
    return out

prep_target_batch = jax.vmap(lambda tokens: jnp.concatenate((tokens[1:], jnp.array([0]))))

@partial(jax.jit, donate_argnums=(0,))
def train_step(state, batch):
    """Performs one supervised fine-tuning step."""
    
    def loss_fn(params):
        # Run the forward pass. The model returns logits.
        logits = state.apply_fn({'params': params}, batch[0]).logits
        
        # Calculate the cross-entropy loss.
        loss = optax.softmax_cross_entropy_with_integer_labels(
            logits=logits, labels=batch[1]
        ).mean()
        
        return loss

    # Compute gradients
    grad_fn = jax.value_and_grad(loss_fn)
    loss, grads = grad_fn(state.params)
    
    # Update the model state
    state = state.apply_gradients(grads=grads)
    
    metrics = {'loss': loss}
    return state, metrics

def train_model(state, text_dl, num_epochs, sharding):
    batchCount = 0
    start_time = time.time()
    for epoch in range(num_epochs):
        start_time = time.time()
        for batch in text_dl:
            if len(batch) % len(jax.devices()) != 0:
              continue  # skip the remaining elements
            input_batch = jnp.array(jnp.array(batch).T)
            target_batch = prep_target_batch(input_batch)
            state, metrics = train_step(state, jax.device_put((input_batch, target_batch), sharding))

            if batchCount % 10 == 0:
                print(f"Loss after batch {batchCount}: {metrics['loss']}")
            batchCount += 1

    end_time = time.time()
    print(f"Completed training model. Total time for training {end_time - start_time} seconds \n")
    return state

def run_training(maxlen, batch_size, datacount):
    print(f"Batch size: {batch_size}, Max length: {maxlen}, Data count: {datacount}")
    #Load the training data
    tiny_stories_dl = load_and_preprocess_data('/data/TinyStories-train.txt', batch_size, maxlen, datacount, tokenizer)
    # Get the Gemma3 model
    model = gm.nn.Gemma3_270M()
    # Load the pretrained parameters
    params = gm.ckpts.load_params(gm.ckpts.CheckpointPath.GEMMA3_270M_PT)
    # Create an optimizer
    optimizer = optax.adamw(learning_rate=learning_rate)
    # Define sharding for data parallel training
    mesh = Mesh(jax.devices(), ('batch',))
    sharding = NamedSharding(mesh, PartitionSpec('batch', None))

    # Testing out current state of the model
    test_prompt = "Once upon a time, there was a girl named Amy."
    generate_text(model, params, tokenizer, test_prompt)

    state = train_state.TrainState.create(
        apply_fn=model.apply,
        params=params,
        tx=optimizer
    )

    # Perform post training
    print("Start training model")
    state = train_model(state, tiny_stories_dl, num_epochs, sharding)

    # Final text generation
    generate_text(model, state.params, tokenizer, test_prompt)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Train Gemma model with custom parameters.')
    parser.add_argument('--maxlen', type=int, default=256, help='Maximum sequence length')
    parser.add_argument('--batch_size', type=int, default=128, help='Batch size')
    parser.add_argument('--datacount', type=int, default=296000, help='Number of data samples to use')
    args = parser.parse_args()

    run_training(maxlen=args.maxlen, batch_size=args.batch_size, datacount=args.datacount)