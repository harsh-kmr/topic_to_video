from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import os
import threading
from generate_video import generate_video_from_topic

app = Flask(__name__)
CORS(app)  # This allows CORS for all domains on all routes

# Global variable to store the status of video generation
video_status = {}

@app.route('/generate_video', methods=['POST'])
def generate_video():
    data = request.json
    topic = data.get('topic')
    if not topic:
        return jsonify({'error': 'No topic provided'}), 400

    # Generate a unique ID for this video generation task
    task_id = str(hash(topic + str(os.urandom(32))))
    
    # Set initial status
    video_status[task_id] = {'status': 'Started', 'progress': 0}

    # Start video generation in a separate thread
    threading.Thread(target=generate_video_thread, args=(topic, task_id)).start()

    return jsonify({'task_id': task_id}), 202

def generate_video_thread(topic, task_id):
    try:
        gemini_api_key = os.environ.get("GEMINI_API_KEY")
        dream_api_key = os.environ.get("DREAM_API_KEY")
        
        if not gemini_api_key or not dream_api_key:
            video_status[task_id] = {'status': 'Failed', 'error': 'API keys not set'}
            return

        output_path = f'videos/{task_id}.mp4'
        os.makedirs('videos', exist_ok=True)

        # Update status for each major step
        video_status[task_id] = {'status': 'Generating script', 'progress': 25}
        script = generate_script_from_topic(gemini_api_key, topic)

        video_status[task_id] = {'status': 'Generating audio', 'progress': 50}
        audio_files = convert_script_to_audio(script)

        video_status[task_id] = {'status': 'Generating images', 'progress': 75}
        image_files = generate_images_from_script(script, dream_api_key)

        video_status[task_id] = {'status': 'Creating video', 'progress': 90}
        video_path = create_video_from_scenes(script, image_files, audio_files, output_path)

        video_status[task_id] = {'status': 'Completed', 'progress': 100, 'video_path': video_path}
    except Exception as e:
        video_status[task_id] = {'status': 'Failed', 'error': str(e)}

@app.route('/video_status/<task_id>', methods=['GET'])
def get_video_status(task_id):
    status = video_status.get(task_id, {'status': 'Not found'})
    return jsonify(status)

@app.route('/download_video/<task_id>', methods=['GET'])
def download_video(task_id):
    status = video_status.get(task_id, {})
    if status.get('status') == 'Completed':
        return send_file(status['video_path'], as_attachment=True)
    else:
        return jsonify({'error': 'Video not ready or not found'}), 404

if __name__ == '__main__':
    app.run(debug=True)