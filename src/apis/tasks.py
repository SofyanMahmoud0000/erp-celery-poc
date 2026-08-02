from flask import Blueprint, jsonify, request

from src.controller.demoController import DemoController
from src.handler.errorHandler import BadRequest

tasks_bp = Blueprint('tasks', __name__, url_prefix='/tasks')


@tasks_bp.route('/finishName', methods=['POST'])
def finish_name():
    name = (request.get_json(silent=True) or {}).get('name')
    if not name:
        raise BadRequest("name is required")
    result = DemoController.finish_name_task.delay(name)
    return jsonify({"task_id": result.id})
