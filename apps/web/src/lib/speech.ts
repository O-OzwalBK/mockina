import { pipeline } from "@huggingface/transformers";

type AudioOutput = {
  audio: Float32Array;
  sampling_rate: number;
};

type SpeechPipeline = (
  input: unknown,
  options?: Record<string, unknown>,
) => Promise<unknown>;

let transcriberPromise: Promise<SpeechPipeline> | undefined;
let ttsPromise: Promise<SpeechPipeline> | undefined;

async function getTranscriber(): Promise<SpeechPipeline> {
  transcriberPromise ??= pipeline(
    "automatic-speech-recognition",
    "Xenova/whisper-tiny.en",
  ) as unknown as Promise<SpeechPipeline>;

  return transcriberPromise;
}

async function getTextToSpeech(): Promise<SpeechPipeline> {
  ttsPromise ??= pipeline(
    "text-to-speech",
    "onnx-community/Supertonic-TTS-ONNX",
  ) as unknown as Promise<SpeechPipeline>;

  return ttsPromise;
}

/**
 * Convert browser-recorded audio to mono, 16 kHz Float32 audio for Whisper.
 * Audio is decoded and processed locally in the browser.
 */
async function decodeTo16kMono(blob: Blob): Promise<Float32Array> {
  const AudioContextClass =
    window.AudioContext ??
    (
      window as Window & {
        webkitAudioContext?: typeof AudioContext;
      }
    ).webkitAudioContext;

  if (!AudioContextClass) {
    throw new Error("Your browser doesn't support audio processing.");
  }

  const context = new AudioContextClass();

  try {
    const buffer = await context.decodeAudioData(await blob.arrayBuffer());

    const mono = new Float32Array(buffer.length);

    for (let channel = 0; channel < buffer.numberOfChannels; channel++) {
      const channelData = buffer.getChannelData(channel);

      for (let i = 0; i < buffer.length; i++) {
        mono[i] += channelData[i] / buffer.numberOfChannels;
      }
    }

    if (buffer.sampleRate === 16000) {
      return mono;
    }

    const outputLength = Math.ceil(mono.length * (16000 / buffer.sampleRate));
    const resampled = new Float32Array(outputLength);
    const ratio = buffer.sampleRate / 16000;

    for (let i = 0; i < outputLength; i++) {
      const sourcePosition = i * ratio;
      const left = Math.floor(sourcePosition);
      const right = Math.min(left + 1, mono.length - 1);
      const fraction = sourcePosition - left;

      resampled[i] =
        (mono[left] ?? 0) * (1 - fraction) + (mono[right] ?? 0) * fraction;
    }

    return resampled;
  } finally {
    await context.close();
  }
}

export async function transcribeRecording(blob: Blob): Promise<string> {
  if (!blob.size) {
    throw new Error("The recording is empty. Please record your answer again.");
  }

  const audio = await decodeTo16kMono(blob);
  const transcriber = await getTranscriber();

  const rawResult = await transcriber(audio, {
    return_timestamps: false,
  });

  const result = rawResult as { text?: string } | Array<{ text?: string }>;
  const text = Array.isArray(result)
    ? result.map((part) => part.text ?? "").join(" ")
    : (result.text ?? "");

  if (!text.trim()) {
    throw new Error(
      "No speech was detected. Try recording a little more clearly.",
    );
  }

  return text.trim();
}

/** Generate a WAV Blob from the model's local audio output. */
function audioToWav(output: AudioOutput): Blob {
  const samples = output.audio;
  const sampleRate = output.sampling_rate;

  if (!samples?.length || !sampleRate) {
    throw new Error("The text-to-speech model returned no audio.");
  }

  const bytesPerSample = 2;
  const dataSize = samples.length * bytesPerSample;
  const buffer = new ArrayBuffer(44 + dataSize);
  const view = new DataView(buffer);

  const writeText = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i++) {
      view.setUint8(offset + i, value.charCodeAt(i));
    }
  };

  writeText(0, "RIFF");
  view.setUint32(4, 36 + dataSize, true);
  writeText(8, "WAVE");
  writeText(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * bytesPerSample, true);
  view.setUint16(32, bytesPerSample, true);
  view.setUint16(34, 16, true);
  writeText(36, "data");
  view.setUint32(40, dataSize, true);

  for (let i = 0; i < samples.length; i++) {
    const sample = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(
      44 + i * bytesPerSample,
      sample < 0 ? sample * 32768 : sample * 32767,
      true,
    );
  }

  return new Blob([buffer], { type: "audio/wav" });
}

export async function generateQuestionAudio(text: string): Promise<Blob> {
  if (!text.trim()) {
    throw new Error("There is no question to read aloud.");
  }

  const tts = await getTextToSpeech();

  const rawOutput = await tts(text.trim(), {
    speaker_embeddings:
      "https://huggingface.co/onnx-community/Supertonic-TTS-ONNX/resolve/main/voices/F1.bin",
    num_inference_steps: 5,
    speed: 1.0,
  });

  return audioToWav(rawOutput as AudioOutput);
}
