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

     

               print("=== /chat start ===")
        print(f"user_input length: {len(user_input)}")

        ai_response = generate_response(user_input)
        print("=== generate_response returned ===")
        print(f"ai_response length: {len(ai_response) if ai_response else 0}")

        audio_response = None
        try:
            audio_response = text_to_speech(ai_response)
            print("=== text_to_speech returned ===")
            print(f"audio_response exists: {audio_response is not None}")
            print(f"audio_response length: {len(audio_response) if audio_response else 0}")
        except Exception as tts_error:
            print("=== TTS exception ===")
            import traceback
            traceback.print_exc()
            print(tts_error)

            print("=== about to jsonify /chat ===")
