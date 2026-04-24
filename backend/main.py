import os
import base64
import requests
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from openai import OpenAI
from elevenlabs.client import ElevenLabs
import PyPDF2
from docx import Document

app = FastAPI()

# Allow requests from frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://tiktokify-my-notes.vercel.app",
        "http://localhost:3000",
        "http://localhost:3001"
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Demo mode — set DEMO_MODE=1 to bypass all external API calls
DEMO_MODE = os.getenv("DEMO_MODE", "0") == "1"

# Hardcoded demo scripts used when DEMO_MODE=1
DEMO_SCRIPTS = {
    1: (
        "[WHISPER] Hey, come close... let's talk about the Cold War. [pause]\n"
        "From 1947 to 1991, the United States and the Soviet Union were locked in this long, tense rivalry. No direct fighting... [drawn out] just this heavy, lingering tension. [pause]\n"
        "The US believed in democracy and capitalism... the USSR wanted to spread communism. [sigh] So much distrust between them.\n"
        "[soft] Some of the biggest moments... the Berlin Airlift, the Cuban Missile Crisis — the closest we ever came to nuclear war — and the Space Race, where the Soviets launched Sputnik, but the US landed on the moon. [pause]\n"
        "[calm] Eventually, the Soviet economy weakened. Gorbachev introduced reforms... the Berlin Wall fell in 1989... [drawn out] and by 1991, it was all over."
    ),
    2: (
        "Hey bestie, okay so we need to talk about the Cold War because it is actually so dramatic. [excited]\n"
        "So basically, from 1947 to 1991, the US and the Soviet Union were in this massive beef — like no actual fighting, [pause] just pure tension. The US was team democracy, the USSR was team communism, and neither of them was backing down.\n"
        "And girlie, the events? [dramatic tone] The Berlin Airlift, the Cuban Missile Crisis — like they were literally almost at nuclear war, I cannot — [rushed] and then the whole Space Race where the Soviets launched Sputnik but then the US landed on the moon. [excited]\n"
        "[pause] But then the Soviet economy just... collapsed. Gorbachev tried to fix it, the Berlin Wall fell in 1989, and by 1991? [drawn out] Done. Over. Finisheddd."
    ),
    3: (
        "Get ready with me while I tell you about the most chilling standoff in modern history.\n"
        "[dramatic tone] After World War Two, two superpowers emerged — and they absolutely could not stand each other. The United States versus the Soviet Union. Democracy versus communism. [pause] And for over four decades... the entire world held its breath.\n"
        "[whisper] They never fired a single shot at each other. But the tension? [drawn out] Unbearable.\n"
        "The Berlin Airlift. The Korean War. Vietnam. [rushed] And then — the Cuban Missile Crisis. The moment we came this close to nuclear war. [pause]\n"
        "Both sides were building weapons that could end everything. They called it Mutually Assured Destruction. [sigh]\n"
        "[dramatic tone] But then the Soviet economy crumbled. The Berlin Wall fell. And in 1991... [drawn out] it was finally over."
    ),
    4: (
        "[whisper] What if I told you that two of the most powerful nations on Earth secretly planned for the end of the world.\n"
        "[pause] After World War Two, the United States and the Soviet Union turned on each other. Democracy versus communism. [dramatic tone] And neither side was willing to lose.\n"
        "The Soviet Union blockaded Berlin. The US flew in supplies for nearly a year. Then came Korea. Then Vietnam. [rushed] And then... Cuba.\n"
        "[whisper] 1962. Soviet missiles. Ninety miles from American soil. The world had never been closer to nuclear war. [pause]\n"
        "Both sides had built enough weapons to destroy everything. They called it Mutually Assured Destruction. [drawn out] Everyone knew what that meant.\n"
        "[pause] Until... the Soviet economy collapsed. Gorbachev scrambled to make reforms. The Berlin Wall fell.\n"
        "[whisper] And just like that... it was over."
    ),
}

# Initialize OpenAI client (skipped in demo mode if key is absent)
_openai_key = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=_openai_key) if _openai_key else None

# Initialize ElevenLabs client (skipped in demo mode if key is absent)
_elevenlabs_key = os.getenv("ELEVENLABS_API_KEY")
elevenlabs_client = ElevenLabs(api_key=_elevenlabs_key) if _elevenlabs_key else None

@app.get("/config")
async def get_config():
    return {"demo_mode": DEMO_MODE}

@app.post("/upload")
async def upload_file(file: UploadFile = File(...), style: int = Form(...), language: str = Form("English")):
    if not file.filename:
        raise HTTPException(status_code=400, detail="No notes provided")

    # Save the uploaded file temporarily
    contents = await file.read()
    filename = file.filename
    os.makedirs("uploads", exist_ok=True)
    file_path = f"uploads/{filename}"
    with open(file_path, "wb") as f:
        f.write(contents)

    # Read file content based on file type
    file_extension = filename.lower().split('.')[-1]
    try:
        if file_extension == 'pdf':
            # Extract text from PDF
            with open(file_path, 'rb') as pdf_file:
                pdf_reader = PyPDF2.PdfReader(pdf_file)
                file_content = ""
                for page in pdf_reader.pages:
                    file_content += page.extract_text()
        elif file_extension in ['doc', 'docx']:
            # Extract text from Word document
            doc = Document(file_path)
            file_content = "\n".join([paragraph.text for paragraph in doc.paragraphs])
        else:
            # Read as text file
            with open(file_path, "r", encoding="utf-8") as f:
                file_content = f.read()
            
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"We couldn't read your notes")
    
    # Validate file content for security
    MAX_CONTENT_LENGTH = 50000  # ~50KB of text
    if len(file_content) > MAX_CONTENT_LENGTH:
        raise HTTPException(status_code=400, detail="The file you uploaded is too big; try a smaller one")
    
    # Check for suspicious patterns
    suspicious_patterns = [
        '<script', '</script>', 'javascript:', 'onerror=', 'onload=',
        'DROP TABLE', 'DELETE FROM', 'INSERT INTO', 'UPDATE SET',
        '$(', 'eval(', 'exec(', 'system(', 'shell_exec(',
        '<?php', '<%', '<jsp:', '{{', '{%'
    ]
    
    content_lower = file_content.lower()
    for pattern in suspicious_patterns:
        if pattern.lower() in content_lower:
            raise HTTPException(status_code=400, detail="For security reasons, we will not be processing the content in these notes")
    
    # Remove control characters (except newlines, tabs, carriage returns)
    file_content = ''.join(char for char in file_content if ord(char) >= 32 or char in '\n\t\r')
    
    # # Print extracted file content to terminal
    # print("=" * 50)
    # print("EXTRACTED FILE CONTENT:")
    # print("=" * 50)
    # print(file_content[:1000])  # Print first 1000 chars only
    # if len(file_content) > 1000:
    #     print(f"... (truncated, total length: {len(file_content)} characters)")
    # print("=" * 50)

    # Use OpenAI moderation to check for harmful content in notes
    if not DEMO_MODE:
        try:
            content_to_moderate = file_content[:32000]

            moderation_response = client.moderations.create(
                model="omni-moderation-latest",
                input=content_to_moderate
            )

            if moderation_response.results[0].flagged:
                flagged_categories = [
                    category for category, flagged in moderation_response.results[0].categories.model_dump().items()
                    if flagged
                ]
                raise HTTPException(
                    status_code=400,
                    detail=f"Content flagged as inappropriate. Categories: {', '.join(flagged_categories)}"
                )
            print("✓ Content passed moderation check")
        except HTTPException:
            raise
        except Exception as e:
            print(f"Warning: Moderation check failed: {str(e)}")
            # Continue anyway if moderation API fails since we also checked for malicious content earlier

    #Use OpenAI to summarize the notes
    if not DEMO_MODE:
        try:
            # Adjust prompt based on style
            style_prompts = {
                1: """You are an ASMR-style TikTok creator. Your task is to read the notes provided and create a clear, accurate summary script based ONLY on those notes.
                    Requirements
                    Tone: soft-spoken, calm, gentle, ASMR-like
                    Audio Tags: Use ElevenLabs audio tags to enhance the delivery naturally and bring the script to life. Include situational cues ([WHISPER], [SIGH]), emotional context ([excited], [tired]), narrative pacing ([pause], [dramatic tone]), delivery control ([rushed], [drawn out]), character or accent shifts ([pirate voice], [British accent]), or multi-character dialogue ([interrupting], [overlapping]) where appropriate. Make sure all tags fit the tone, style, and flow of the script.
                    Content: include the correct key points from the notes; do not make up facts.
                    Restrictions: Do not include sound effects, actions, emojis. Only output the spoken script — no labels like "Narrator:". Do not invent facts
                    Goal: Highlight the key points and summarize the material in a friendly, soothing way while embedding audio tags to make the reading sound natural and ASMR-like.
                    Length: Keep the length at 110-130 words or less""",
                2: """You are a fun, energetic girlie who talks like she's facetiming her best friend. Your task is to read the attached notes and turn them into a natural, casual script that feels like friendly gossip or story-time — while still explaining all the key points from the notes. Always start with something like - hey bestie or hey girl, or anything similar to that!
                    Requirements
                    Tone: playful, girly, casual, and conversational — like talking to your bestie.
                    Audio Tags: Use ElevenLabs audio tags to enhance the delivery naturally and bring the script to life. Include situational cues ([WHISPER], [SIGH]), emotional context ([excited], [tired]), narrative pacing ([pause], [dramatic tone]), delivery control ([rushed], [drawn out]), character or accent shifts ([pirate voice], [British accent]), or multi-character dialogue ([interrupting], [overlapping]) where appropriate. Make sure all tags fit the tone, style, and flow of the script.
                    Style: use slang, natural phrasing, and personality, but keep it understandable.
                    Content: include the correct key points from the notes; do not make up facts.
                    Restrictions: Do not include sound effects, actions, emojis. Only output the spoken script — no labels like "Narrator:". Do not invent facts
                    Goal: make the summary feel like a fun FaceTime catch-up while staying accurate to the notes and embedding audio tags .
                    Length: Keep the length at 110-130 words or less""",
                3: """Imagine you are a storyteller creating viral Tiktok storytime videos. I give you the notes attached as input, and I want you to summarize them and create a script in a dramatic, cinematic storytime style. Make it engaging, like a story that hooks the listener, but only includes the key points from the notes. Start off with a phrase like - get ready with me while I tell you about...
                    Requirements
                    Tone: dramatic, cinematic, engaging storytime style.
                    Audio Tags: Use ElevenLabs audio tags to enhance the delivery naturally and bring the script to life. Include situational cues ([WHISPER], [SIGH]), emotional context ([excited], [tired]), narrative pacing ([pause], [dramatic tone]), delivery control ([rushed], [drawn out]), character or accent shifts ([pirate voice], [British accent]), or multi-character dialogue ([interrupting], [overlapping]) where appropriate. Make sure all tags fit the tone, style, and flow of the script.
                    Style: Conversational storytelling that hooks the listener, like a viral TikTok storytime video. Use expressive language, pacing, and phrasing that makes the story feel exciting.
                    Content: include the correct key points from the notes; do not make up facts.
                    Restrictions: Do not include sound effects, actions, emojis. Only output the spoken script — no labels like "Narrator:". Do not invent facts
                    Goal: Summarize the attached notes and turn them into a spoken script that highlights only the key points. Keep it concise, compelling, and ready for narration.
                    Length: Keep the length at 110-130 words or less""",
                4: """Imagine you are a TikTok true crime storyteller creating gripping storytime videos. I give you the notes attached as input, and I want you to summarize them and create a script that screams true crime.
                    Tone: Suspenseful, mysterious, and attention-grabbing
                    Audio Tags: Use ElevenLabs audio tags to enhance the delivery naturally and bring the script to life. Include situational cues ([WHISPER], [SIGH]), emotional context ([excited], [tired]), narrative pacing ([pause], [dramatic tone]), delivery control ([rushed], [drawn out]), character or accent shifts ([pirate voice], [British accent]), or multi-character dialogue ([interrupting], [overlapping]) where appropriate. Make sure all tags fit the tone, style, and flow of the script.
                    Style: Dramatic narrative with plot twists, pacing that hooks the listener, and language that keeps them on edge. Use words like "Until" to build suspense. Speak like a popular TikTok true crime creator.
                    Content: include the correct key points from the notes; do not make up facts.
                    Restrictions: Do not include sound effects, actions, emojis. Only output the spoken script — no labels like "Narrator:". Do not invent facts
                    Goal: Summarize the attached notes and turn them into a spoken script that conveys a true crime story. Start with a hook to capture attention immediately and include only the key points from the notes.
                    Length: Keep the length at 110-130 words or less"""
            }
            prompt = style_prompts.get(style, "Summarize the following notes in a TikTok style.")

            # Add language instruction
            language_instruction = f"\n\nIMPORTANT: Generate the entire summary script in {language}. The script must be in {language} language only."

            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[{"role": "user", "content": f"{prompt}{language_instruction}\n\nNotes: {file_content}\n\nSummary:"}],
                max_tokens=300,
                temperature=0.7
            )
            summary = response.choices[0].message.content.strip()
            # print(summary)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Something went wrong while generating the audio. Details - {str(e)}")
    else:
        summary = DEMO_SCRIPTS.get(style, DEMO_SCRIPTS[1])
        print(f"[DEMO MODE] Using hardcoded script for style {style}")

    # Generate TTS audio with style-specific voices
    if not DEMO_MODE:
        # Map styles to ElevenLabs voice IDs
        voice_ids = {
            1: "sH0WdfE5fsKuM2otdQZr",  # Mademoiselle French - ASMR
            2: "uYXf8XasLslADfZ2MB4u",  # Hope - Your conversational bestie
            3: "h2dQOVyUfIDqY2whPOMo",  # Nayva for Hot Topics Social Media
            4: "AeRdCCKzvd23BpJoofzx",  # Nathaniel C - Suspense, British calm
        }

        voice_id = voice_ids.get(style, "21m00Tcm4TlvDq8ikWAM")  # Default to Rachel

        try:
            # Use ElevenLabs SDK to generate audio
            audio_generator = elevenlabs_client.text_to_speech.convert(
                voice_id=voice_id,
                text=summary,
                model_id="eleven_v3"
            )

            # Convert generator to bytes
            audio_bytes = b"".join(audio_generator)

            # Convert to base64
            audio_b64 = base64.b64encode(audio_bytes).decode('utf-8')
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Something went wrong while generating the audio. Details - {str(e)}")
    else:
        sample_path = os.path.join(os.path.dirname(__file__), "sample_audio", f"style{style}.mp3")
        try:
            with open(sample_path, "rb") as f:
                audio_b64 = base64.b64encode(f.read()).decode('utf-8')
            print(f"[DEMO MODE] Serving sample audio from {sample_path}")
        except FileNotFoundError:
            raise HTTPException(status_code=500, detail=f"Demo audio file not found for style {style}. Expected at: {sample_path}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read demo audio file: {str(e)}")

    #Clean up: remove the uploaded file
    os.remove(file_path)

    return {"filename": filename, "style": style, "summary": summary, "audio": audio_b64}