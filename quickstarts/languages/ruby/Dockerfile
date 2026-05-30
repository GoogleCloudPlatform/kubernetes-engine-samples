# Use the official lightweight Ruby image.
# https://hub.docker.com/_/ruby
FROM ruby:3.3-slim
ENV RACK_ENV=production

# Install production dependencies.
WORKDIR /usr/src/app
COPY Gemfile Gemfile.lock ./
RUN apt-get update && apt-get install -y --no-install-recommends build-essential \
    && bundle install \
    && apt-get purge -y --auto-remove build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy local code to the container image.
COPY . ./

# Run the web service on container startup.
CMD ["bundle", "exec", "ruby", "./app.rb"]
