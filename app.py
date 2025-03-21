from flask import Flask, request, render_template, jsonify
import os
import speech_recognition as sr
from pydub import AudioSegment
import uuid
import time
import subprocess

# Set environment variables for FFmpeg - this is more reliable than the AudioSegment.converter approach
os.environ["PATH"] += os.pathsep + r"C:\Users\Hp\Downloads\ffmpeg-master-latest-win64-gpl-shared\bin"

# Another way to configure pydub to use FFmpeg
from pydub.utils import which
AudioSegment.converter = which("ffmpeg.exe") or r"C:\Users\Hp\Downloads\ffmpeg-master-latest-win64-gpl-shared\bin\ffmpeg.exe"
AudioSegment.ffmpeg = which("ffmpeg.exe") or r"C:\Users\Hp\Downloads\ffmpeg-master-latest-win64-gpl-shared\bin\ffmpeg.exe"
AudioSegment.ffprobe = which("ffprobe.exe") or r"C:\Users\Hp\Downloads\ffmpeg-master-latest-win64-gpl-shared\bin\ffprobe.exe"

# Verify FFmpeg is accessible
try:
    subprocess.run([AudioSegment.converter, "-version"], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    print("FFmpeg is configured correctly!")
except Exception as e:
    print(f"FFmpeg configuration error: {e}")
    print(f"Current FFmpeg path: {AudioSegment.converter}")

app = Flask(__name__)

# Configure upload folder
UPLOAD_FOLDER = 'uploads'
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Configure maximum content length for uploads (50MB)
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'}), 400
    
    file = request.files['file']
    
    if file.filename == '':
        return jsonify({'error': 'No selected file'}), 400
    
    if file:
        # Create unique filename to prevent collisions
        original_filename = file.filename
        file_extension = os.path.splitext(original_filename)[1].lower()
        
        if file_extension != '.mp3':
            return jsonify({'error': 'Only MP3 files are supported'}), 400
        
        unique_filename = str(uuid.uuid4()) + file_extension
        file_path = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
        
        # Save the file
        file.save(file_path)
        print(f"File saved to: {file_path}")
        
        try:
            # Process the file
            transcription = process_audio_file(file_path)
            
            # Return response
            return jsonify({
                'success': True,
                'transcription': transcription,
                'original_filename': original_filename
            })
        except Exception as e:
            import traceback
            print(f"Error processing file: {str(e)}")
            print(traceback.format_exc())
            return jsonify({'error': str(e)}), 500
        finally:
            # Clean up in the finally block to ensure it runs
            try:
                # Sleep briefly to allow file handles to be released
                time.sleep(1)
                if os.path.exists(file_path):
                    os.remove(file_path)
                    print(f"Removed file: {file_path}")
            except Exception as clean_up_error:
                print(f"Failed to remove file {file_path}: {str(clean_up_error)}")
    
    return jsonify({'error': 'Unknown error occurred'}), 500

def process_audio_file(file_path):
    """Process MP3 audio file and return transcription"""
    # Convert MP3 to WAV
    wav_path = file_path.replace('.mp3', '.wav')
    
    try:
        print(f"Converting {file_path} to WAV format...")
        
        # Try an alternative approach if pydub fails
        try:
            # First attempt with pydub
            sound = AudioSegment.from_mp3(file_path)
            sound.export(wav_path, format="wav")
        except Exception as e:
            print(f"Pydub conversion failed: {e}")
            print("Trying direct FFmpeg conversion...")
            
            # Direct FFmpeg conversion as fallback
            ffmpeg_path = r"C:\Users\Hp\Downloads\ffmpeg-master-latest-win64-gpl-shared\bin\ffmpeg.exe"
            subprocess.run([ffmpeg_path, "-i", file_path, wav_path], check=True)
        
        print(f"Successfully converted to WAV: {wav_path}")
        
        # Transcribe the audio file
        transcription = transcribe_large_audio(wav_path)
        return transcription
    finally:
        # Clean up the temporary WAV file
        try:
            if os.path.exists(wav_path):
                os.remove(wav_path)
                print(f"Removed temporary WAV file: {wav_path}")
        except Exception as e:
            print(f"Could not remove temporary WAV file {wav_path}: {str(e)}")

def transcribe_large_audio(file_path, chunk_duration_seconds=30):
    """Transcribe audio file by processing it in chunks"""
    recognizer = sr.Recognizer()
    
    try:
        print(f"Opening WAV file for transcription: {file_path}")
        sound = AudioSegment.from_wav(file_path)
        
        # Split audio into chunks to avoid timeout
        chunk_length_ms = chunk_duration_seconds * 1000
        chunks = [sound[i:i+chunk_length_ms] for i in range(0, len(sound), chunk_length_ms)]
        print(f"Split audio into {len(chunks)} chunks")
        
        full_text = []
        
        for i, chunk in enumerate(chunks):
            # Export chunk to temporary file
            chunk_file = f"temp_chunk_{i}.wav"
            
            try:
                # Export chunk to temporary file
                chunk.export(chunk_file, format="wav")
                print(f"Processing chunk {i+1}/{len(chunks)}")
                
                # Transcribe chunk
                with sr.AudioFile(chunk_file) as source:
                    audio_data = recognizer.record(source)
                    text = recognizer.recognize_google(audio_data)
                    full_text.append(text)
                    print(f"Chunk {i+1} transcription: {text[:30]}...")
            except sr.UnknownValueError:
                print(f"Could not understand audio in chunk {i+1}")
            except sr.RequestError as e:
                print(f"Google Speech API error in chunk {i+1}: {e}")
            except Exception as e:
                print(f"Error transcribing chunk {i+1}: {e}")
            finally:
                # Always clean up temp files
                if os.path.exists(chunk_file):
                    try:
                        os.remove(chunk_file)
                    except Exception as e:
                        print(f"Could not remove chunk file {chunk_file}: {str(e)}")
        
        # Return the combined transcription
        if not full_text:
            return "No speech could be recognized in the audio file."
        return " ".join(full_text)
    except Exception as e:
        print(f"Error in transcribe_large_audio: {str(e)}")
        raise

if __name__ == '__main__':
    app.run(debug=True)