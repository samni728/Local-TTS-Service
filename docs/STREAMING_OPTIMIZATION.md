# Streaming Playback Optimization

This document gives an overview of how LocalTTS performs streaming audio playback and highlights the tunable options that affect performance.

## Overview of the Streaming Flow

1. **Text preprocessing** – input text is cleaned and split into chunks according to `CHUNK_SIZE`.
2. **Hybrid generation** – the first few chunks defined by `SYNC_CHUNKS` are generated synchronously so that playback can start immediately.
3. **Concurrent processing** – remaining chunks are processed in parallel with a concurrency limit of `MAX_CONCURRENT_REQUESTS`.
4. **Ordered output** – generated audio data is buffered and yielded in original chunk order so the client receives a seamless stream.

This design tries to minimise initial delay while still fully utilising concurrency for long text.

## Configuration Options

- **`CHUNK_SIZE`**
  - Maximum length of each text chunk when splitting the input.
  - Smaller values reduce the risk of request failure but increase the number of chunks.
  - Recommended range: 200‑600 characters. Increase if network is stable and you want fewer requests.
- **`MAX_CONCURRENT_REQUESTS`**
  - Limits how many TTS requests are issued at the same time.
  - Higher values improve throughput but consume more system resources.
  - Start around 10‑20 and adjust based on CPU/network load.
- **`SYNC_CHUNKS`**
  - Number of chunks generated sequentially before switching to concurrent mode.
  - A small value lets concurrency kick in earlier but may delay the first audio bytes slightly.
  - Typical value is 2‑4; lower if you want faster scaling, higher for extremely short texts.

Tuning these parameters depends on your hardware and the typical length of input text. Test with realistic workloads to find the best balance between latency and throughput.

## Potential Optimisation Directions

- Reduce the number of synchronous chunks so concurrency starts sooner.
- Increase parallelism carefully by raising `MAX_CONCURRENT_REQUESTS`.
- Replace the polling loop that waits for ready buffers with a queue or other notification mechanism.
- Explore streaming directly from Edge TTS (send each chunk to the client as it is produced) instead of waiting for full chunk generation.

