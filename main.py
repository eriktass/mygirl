@app.route('/chat', methods=['POST'])
    def chat():
        data = request.json
        message = data.get('message')
        if not message:
            return jsonify({'error': 'No message provided'}), 400

        try:
            if ELEVENLABS_API_KEY and VOICE_ID:
                audio_response = generate_audio_response(message)
            else:
                audio_response = None

            return jsonify({'message': message, 'audio_response': audio_response})
        except Exception as e:
            return jsonify({'error': str(e)}), 500