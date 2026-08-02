from flask import Blueprint, jsonify

from src.controller.beatTimeController import BeatTimeController

health_bp = Blueprint('health', __name__, url_prefix='/health')


@health_bp.route('', methods=['GET'])
def health():
    return jsonify({"status": "ok"})


@health_bp.route('/beatStatus', methods=['GET'])
def beat_status():
    return jsonify(BeatTimeController.is_beat_healthy())
