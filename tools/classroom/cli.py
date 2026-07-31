"""
Classroom Listener — real-time question detection and answering.

Listens via microphone, transcribes speech with faster-whisper,
sends every utterance to Sonnet 4.6 on OpenRouter to detect and answer
teacher questions.
"""

import argparse
import collections
import os
import queue
import sys
import threading
import time
from datetime import datetime

import numpy as np
import sounddevice as sd
import torch
from faster_whisper import WhisperModel
from openai import OpenAI

# ── Constants ──────────────────────────────────────────────────────────

SAMPLE_RATE = 16000
FRAME_SAMPLES = 512  # 32ms — Silero VAD minimum
SILENCE_FRAMES = 25  # ~800ms of silence to end utterance
MIN_SPEECH_FRAMES = 15  # ~480ms minimum speech to transcribe
MAX_SPEECH_SECONDS = 8  # force-flush after this many seconds of continuous speech
MAX_SPEECH_FRAMES = int(MAX_SPEECH_SECONDS * SAMPLE_RATE / FRAME_SAMPLES)
CONTEXT_WINDOW = 20  # rolling transcript lines for LLM context
DEFAULT_WHISPER_MODEL = "small.en"

# ── ANSI helpers ───────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
DIM = "\033[2m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
CYAN = "\033[36m"


def clear_screen():
    print("\033[2J\033[H", end="", flush=True)


# ── VAD ────────────────────────────────────────────────────────────────

def load_vad():
    model, _ = torch.hub.load("snakers4/silero-vad", "silero_vad", trust_repo=True)
    model.reset_states()
    return model


def is_speech(vad_model, audio_chunk: np.ndarray) -> bool:
    # Normalize int16 to [-1, 1] float32 using fixed scale (not per-frame max)
    tensor = torch.from_numpy(audio_chunk.astype(np.float32) / 32768.0)
    confidence = vad_model(tensor, SAMPLE_RATE).item()
    return confidence > 0.3  # lower threshold for quiet/distant audio


# ── Transcription ──────────────────────────────────────────────────────

def load_whisper(model_size: str = DEFAULT_WHISPER_MODEL) -> WhisperModel:
    return WhisperModel(model_size, device="cpu", compute_type="int8")


def transcribe(model: WhisperModel, audio: np.ndarray) -> str:
    audio_f32 = audio.astype(np.float32) / 32768.0
    segments, _ = model.transcribe(
        audio_f32, beam_size=5, language="en",
        without_timestamps=True, vad_filter=False,
    )
    return " ".join(seg.text.strip() for seg in segments).strip()


# ── LLM Question Detection + Answering ────────────────────────────────

SYSTEM_PROMPT = """\
You are a silent classroom assistant for an AP European History class.

You receive real-time transcript snippets from a classroom. Your job:
1. Determine if the utterance contains a SUBSTANTIVE QUESTION about history, politics, economics, culture, or any academic topic.
2. If yes, provide a clear, concise answer (2-4 sentences max).
3. If no question is present, respond with exactly: NO_QUESTION

Answer these kinds of questions:
- Direct questions: "What caused the French Revolution?"
- Implied questions: "I'm wondering what decolonization looked like..."
- Prompts for analysis: "So how does this connect to the Cold War?"
- Any utterance seeking factual/analytical information about history

Do NOT answer (respond NO_QUESTION):
- Classroom management: "did everyone turn in homework?", "open your books"
- Social/phatic: "how are you?", "good morning"
- Meta: "any questions?", "does that make sense?"
- Pure statements with no question or inquiry

Keep answers factual, specific, AP Euro level. Include dates and key names.

Recent classroom context:
{context}

Latest utterance to evaluate:
{utterance}"""


def query_llm(client: OpenAI, model: str, context: list[str], utterance: str) -> str | None:
    ctx_text = "\n".join(context[-CONTEXT_WINDOW:]) if context else "(no prior context)"
    prompt = SYSTEM_PROMPT.format(context=ctx_text, utterance=utterance)
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            max_tokens=300,
            temperature=0.2,
        )
        content = response.choices[0].message.content
        if not content:
            return None
        answer = content.strip()
        if "NO_QUESTION" in answer:
            return None
        return answer
    except Exception as e:
        return f"[LLM Error: {e}]"


# ── Display ────────────────────────────────────────────────────────────

class Display:
    """Thread-safe terminal display. Only redraws when dirty."""

    def __init__(self):
        self.transcript: list[tuple[str, str]] = []
        self.answers: list[tuple[str, str, str]] = []
        self.status = "Listening..."
        self.lock = threading.Lock()
        self._dirty = True

    def add_transcript(self, text: str):
        with self.lock:
            ts = datetime.now().strftime("%H:%M:%S")
            self.transcript.append((ts, text))
            if len(self.transcript) > 50:
                self.transcript = self.transcript[-50:]
            self._dirty = True

    def add_answer(self, question: str, answer: str):
        with self.lock:
            ts = datetime.now().strftime("%H:%M:%S")
            self.answers.append((ts, question, answer))
            self._dirty = True

    def set_status(self, status: str):
        with self.lock:
            if status != self.status:
                self.status = status
                self._dirty = True

    def render_if_dirty(self):
        with self.lock:
            if not self._dirty:
                return
            self._dirty = False

            clear_screen()
            print(f"{BOLD}{CYAN}  CLASSROOM LISTENER{RESET}  {DIM}{self.status}{RESET}")
            print(f"{DIM}  {'=' * 60}{RESET}\n")

            print(f"  {BOLD}TRANSCRIPT{RESET}")
            if not self.transcript:
                print(f"  {DIM}(waiting for speech...){RESET}")
            for ts, text in self.transcript[-12:]:
                print(f"  {DIM}{ts}{RESET}  {text}")
            print()

            print(f"  {BOLD}{GREEN}ANSWERS{RESET}")
            if not self.answers:
                print(f"  {DIM}(no questions detected yet){RESET}")
            for ts, q, a in self.answers[-5:]:
                print(f"  {DIM}{ts}{RESET}  {YELLOW}{BOLD}Q: {q}{RESET}")
                print(f"         {GREEN}{BOLD}A: {a}{RESET}")
                print()
            sys.stdout.flush()


# ── Main pipeline ─────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Classroom question listener")
    parser.add_argument("--model", default=DEFAULT_WHISPER_MODEL,
                        help="Whisper model size (default: base.en)")
    parser.add_argument("--device", type=int, default=None,
                        help="Audio input device index")
    parser.add_argument("--list-devices", action="store_true")
    parser.add_argument("--llm-model", default="anthropic/claude-sonnet-4.6",
                        help="OpenRouter model (default: anthropic/claude-sonnet-4.6)")
    args = parser.parse_args()

    if args.list_devices:
        for i, d in enumerate(sd.query_devices()):
            if d["max_input_channels"] > 0:
                marker = " (default)" if i == sd.default.device[0] else ""
                print(f"  [{i}] {d['name']}{marker}")
        return

    api_key = os.environ.get("OPENROUTER_API_KEY")
    if not api_key:
        print("Error: OPENROUTER_API_KEY not set", file=sys.stderr)
        sys.exit(1)

    print(f"{BOLD}Loading models...{RESET}", flush=True)
    print("  Silero VAD...", flush=True)
    vad_model = load_vad()
    print(f"  Whisper ({args.model})...", flush=True)
    whisper_model = load_whisper(args.model)
    print("  OpenRouter...", flush=True)
    llm_client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)

    display = Display()
    context: list[str] = []

    # ── Audio callback -> frame queue ──
    frame_queue: queue.Queue[np.ndarray] = queue.Queue()

    def audio_callback(indata, frames, time_info, status):
        frame_queue.put(indata[:, 0].copy())

    stream = sd.InputStream(
        samplerate=SAMPLE_RATE, channels=1, dtype="int16",
        blocksize=FRAME_SAMPLES, device=args.device,
        callback=audio_callback,
    )

    # ── Process utterance (transcribe + LLM) in background ──
    def process_utterance(audio: np.ndarray):
        display.set_status("Transcribing...")
        text = transcribe(whisper_model, audio)
        if not text or len(text.strip()) < 3:
            display.set_status("Listening...")
            return

        display.add_transcript(text)
        context.append(text)
        if len(context) > CONTEXT_WINDOW:
            context.pop(0)

        display.set_status(f"Analyzing: {text[:50]}...")
        answer = query_llm(llm_client, args.llm_model, context, text)
        if answer:
            display.add_answer(text, answer)
        display.set_status("Listening...")

    # ── VAD loop in separate thread ──
    stop_event = threading.Event()

    def vad_loop():
        ring_buffer = collections.deque(maxlen=SILENCE_FRAMES)
        speech_buffer: list[np.ndarray] = []
        triggered = False

        while not stop_event.is_set():
            try:
                chunk = frame_queue.get(timeout=0.1)
            except queue.Empty:
                continue

            speech = is_speech(vad_model, chunk)

            if not triggered:
                ring_buffer.append((chunk, speech))
                num_voiced = sum(1 for _, s in ring_buffer if s)
                if num_voiced > 0.75 * ring_buffer.maxlen:
                    triggered = True
                    speech_buffer = [f for f, _ in ring_buffer]
                    ring_buffer.clear()
                    display.set_status("Hearing speech...")
            else:
                speech_buffer.append(chunk)
                ring_buffer.append((chunk, speech))
                num_unvoiced = sum(1 for _, s in ring_buffer if not s)

                should_flush = False

                # Silence detected — end of utterance
                if num_unvoiced > 0.75 * ring_buffer.maxlen:
                    triggered = False
                    should_flush = True
                    ring_buffer.clear()
                    vad_model.reset_states()

                # Force-flush long continuous speech
                elif len(speech_buffer) >= MAX_SPEECH_FRAMES:
                    should_flush = True
                    # Stay triggered, keep listening

                if should_flush and len(speech_buffer) >= MIN_SPEECH_FRAMES:
                    audio = np.concatenate(speech_buffer)
                    speech_buffer = []
                    # Process in background thread so VAD keeps running
                    threading.Thread(target=process_utterance, args=(audio,), daemon=True).start()
                elif should_flush:
                    speech_buffer = []

    # ── Start everything ──
    stream.start()
    vad_thread = threading.Thread(target=vad_loop, daemon=True)
    vad_thread.start()

    print(f"\n{BOLD}{GREEN}Ready! Ctrl+C to stop.{RESET}\n", flush=True)
    time.sleep(0.5)

    try:
        while True:
            display.render_if_dirty()
            time.sleep(0.2)
    except KeyboardInterrupt:
        print(f"\n{BOLD}Stopped.{RESET}")
        stop_event.set()
        stream.stop()
        stream.close()


if __name__ == "__main__":
    main()
