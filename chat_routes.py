import json
import uuid
from flask import Blueprint, request, jsonify
from models import db, ChatSession, ChatMessage
from services.ollama_service import OllamaService

chat_bp = Blueprint('chat', __name__, url_prefix='/api/chat')

@chat_bp.route('', methods=['POST'])
def send_chat_message():
    data = request.get_json() or {}
    user_message = data.get('message', '').strip()
    session_id = data.get('session_id') or str(uuid.uuid4())

    if not user_message:
        return jsonify({'error': 'Message cannot be empty'}), 400

    # Ensure session exists
    session = ChatSession.query.get(session_id)
    if not session:
        session = ChatSession(id=session_id, title=user_message[:30])
        db.session.add(session)
        db.session.flush()

    # Save user message
    user_msg_entry = ChatMessage(
        session_id=session_id,
        role='user',
        content=user_message
    )
    db.session.add(user_msg_entry)

    # Generate AI response via Ollama / intelligent retail engine
    ai_result = OllamaService.generate_chat_response(user_message)
    reply_text = ai_result.get('reply', '')
    structured_data = ai_result.get('data', [])

    # Save assistant message
    ai_msg_entry = ChatMessage(
        session_id=session_id,
        role='assistant',
        content=reply_text,
        data_json=json.dumps(structured_data) if structured_data else None
    )
    db.session.add(ai_msg_entry)
    db.session.commit()

    return jsonify({
        'session_id': session_id,
        'reply': reply_text,
        'data': structured_data,
        'generated_by': ai_result.get('generated_by', 'inventra-ai'),
        'context_summary': ai_result.get('context_summary', {})
    }), 200

@chat_bp.route('/history', methods=['GET'])
def get_chat_history():
    session_id = request.args.get('session_id')
    if not session_id:
        # Return recent messages from latest session
        latest_session = ChatSession.query.order_by(ChatSession.created_at.desc()).first()
        if not latest_session:
            return jsonify({'messages': [], 'session_id': str(uuid.uuid4())}), 200
        session_id = latest_session.id

    messages = ChatMessage.query.filter_by(session_id=session_id).order_by(ChatMessage.created_at.asc()).all()
    return jsonify({
        'session_id': session_id,
        'messages': [m.to_dict() for m in messages]
    }), 200

@chat_bp.route('/history', methods=['DELETE'])
def clear_chat_history():
    session_id = request.args.get('session_id')
    if session_id:
        ChatMessage.query.filter_by(session_id=session_id).delete()
        ChatSession.query.filter_by(id=session_id).delete()
        db.session.commit()
    return jsonify({'message': 'Conversation cleared'}), 200
