import google.generativeai as genai
import os
import json
from melo.api import TTS
import requests
import time
from moviepy.editor import ImageClip, AudioFileClip, concatenate_videoclips

def generate_script_from_topic(api_key, topic):
    # Configure the Gemini API
    genai.configure(api_key=api_key)

    # Initialize the model
    model = genai.GenerativeModel('gemini-1.5-flash',
                                  generation_config={"response_mime_type": "application/json"})

    # Prepare the prompt
    prompt = f"""
    You are part of a short video generation pipeline. Create a script for a video about the following topic:

    {topic}

    Think like a script writer who has 2 available tools (text-to-speech and text-to-image).  use hooks to grab attention in first scene.

    Your output should be in JSON format with scene number as key. Use the following format:

    {{
    "1": {{
        "image": "Write a prompt for generating an image relevant to the scene",
        "text": "Narration text for text-to-speech"
    }},
    "2": {{
        "image": "...",
        "text": "..."
    }},
    ...
    }}

    Create as many scenes as necessary to cover the topic comprehensively, typically between 3 to 7 scenes.
    Ensure each scene's text is concise and suitable for a short video (around 20-30 seconds per scene).
    """

    try:
        # Generate content
        response = model.generate_content(prompt)
        
        # Parse the JSON response
        script = json.loads(response.text)
        
        return script
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return None

def convert_script_to_audio(script, output_directory='audio_files', speed=1.0):
    # Initialize TTS model
    model = TTS(language='EN', device='auto')
    speaker_ids = model.hps.data.spk2id

    # Create output directory if it doesn't exist
    os.makedirs(output_directory, exist_ok=True)

    audio_files = {}

    for scene_num, scene_data in script.items():
        text = scene_data['text']
        output_path = os.path.join(output_directory, f'scene_{scene_num}.wav')

        try:
            # Generate audio with American accent
            model.tts_to_file(text, speaker_ids['EN-US'], output_path, speed=speed)
            audio_files[scene_num] = output_path
            print(f"Generated audio for scene {scene_num}: {output_path}")
        except Exception as e:
            print(f"Error generating audio for scene {scene_num}: {str(e)}")

    return audio_files

BASE_URL = "https://api.luan.tools/api/tasks/"

def generate_images_from_script(script, api_key, style_id=1, output_directory='image_files'):
    """
    Generate images for each scene in the script using the Dream API.
    
    :param script: Dictionary containing the script with scene numbers as keys
    :param api_key: API key for the Dream API
    :param style_id: Style ID for image generation (default is 17 for 'Realistic')
    :param output_directory: Directory to save generated images
    :return: Dictionary mapping scene numbers to image file paths
    """
    HEADERS = {
        'Authorization': f'bearer {api_key}',
        'Content-Type': 'application/json'
    }

    # Create output directory if it doesn't exist
    os.makedirs(output_directory, exist_ok=True)

    image_files = {}

    for scene_num, scene_data in script.items():
        prompt = scene_data['image']
        output_path = os.path.join(output_directory, f'scene_{scene_num}.jpg')

        try:
            # Step 1: POST request to create a task
            post_payload = json.dumps({"use_target_image": False})
            post_response = requests.post(BASE_URL, headers=HEADERS, data=post_payload)
            post_response.raise_for_status()
            task_id = post_response.json()['id']

            # Step 2: PUT request to update the task with image details
            task_id_url = f"{BASE_URL}{task_id}"
            put_payload = json.dumps({
                "input_spec": {
                    "style": style_id,
                    "prompt": prompt,
                    "width": 540,
                    "height": 960  # 16:9 aspect ratio
                }
            })
            put_response = requests.put(task_id_url, headers=HEADERS, data=put_payload)
            put_response.raise_for_status()

            # Step 3: Poll for image generation completion
            while True:
                response = requests.get(task_id_url, headers=HEADERS)
                response.raise_for_status()
                response_json = response.json()

                state = response_json["state"]

                if state == "completed":
                    image_response = requests.get(response_json["result"])
                    image_response.raise_for_status()
                    with open(output_path, "wb") as image_file:
                        image_file.write(image_response.content)
                    print(f"Image for scene {scene_num} saved successfully: {output_path}")
                    image_files[scene_num] = output_path
                    break
                elif state == "failed":
                    print(f"Image generation failed for scene {scene_num}")
                    break

                time.sleep(3)

        except Exception as e:
            print(f"Error generating image for scene {scene_num}: {str(e)}")

    return image_files

def create_video_from_scenes(script, image_files, audio_files, output_path='output_video.mp4'):
    """
    Create a video from the generated images and audio files.
    
    :param script: Dictionary containing the script with scene numbers as keys
    :param image_files: Dictionary mapping scene numbers to image file paths
    :param audio_files: Dictionary mapping scene numbers to audio file paths
    :param output_path: Path where the output video will be saved
    :return: Path to the created video file
    """
    clips = []

    for scene_num in sorted(script.keys()):
        image_path = image_files.get(scene_num)
        audio_path = audio_files.get(scene_num)

        if image_path and audio_path:
            # Load the image and audio
            image_clip = ImageClip(image_path)
            audio_clip = AudioFileClip(audio_path)

            # Set the duration of the image clip to match the audio duration
            image_clip = image_clip.set_duration(audio_clip.duration)

            # Set the audio of the image clip
            video_clip = image_clip.set_audio(audio_clip)

            clips.append(video_clip)
        else:
            print(f"Warning: Missing image or audio for scene {scene_num}")

    # Concatenate all the clips
    final_clip = concatenate_videoclips(clips)

    # Write the result to a file
    final_clip.write_videofile(output_path, codec='libx264', audio_codec='aac', fps=24)

    return output_path

def generate_video_from_topic(topic, gemini_api_key, dream_api_key, output_path='output_video.mp4'):
    print(f"Generating script for topic: {topic}")
    script = generate_script_from_topic(gemini_api_key, topic)
    print("Script generated successfully.")

    print("Converting script to audio...")
    audio_files = convert_script_to_audio(script)
    print("Audio files generated successfully.")

    print("Generating images for the script...")
    image_files = generate_images_from_script(script, dream_api_key)
    print("Image files generated successfully.")

    print("Creating final video...")
    video_path = create_video_from_scenes(script, image_files, audio_files, output_path)
    print(f"Video created successfully: {video_path}")
    
    return video_path

if __name__ == "__main__":
    topic = "Greek Mythology"

    if not gemini_api_key or not dream_api_key:
        print("Please set the GEMINI_API_KEY and DREAM_API_KEY environment variables.")
    else:
        video_path = generate_video_from_topic(topic, gemini_api_key, dream_api_key)
        if video_path:
            print(f"Video created successfully: {video_path}")
        else:
            print("Failed to create video.")