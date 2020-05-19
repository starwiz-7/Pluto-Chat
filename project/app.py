from datetime import datetime

from bson.json_util import dumps
from flask import Flask, render_template, request, redirect, url_for
from flask_login import LoginManager, login_user, login_required, logout_user, current_user
from flask_socketio import SocketIO, join_room, leave_room
from pymongo.errors import DuplicateKeyError
from flask_pymongo import PyMongo

from db import get_user, save_user, save_room, add_room_members, get_rooms_for_user, get_room, is_room_member, \
    get_room_members, is_room_admin, update_room, remove_room_members, save_message, get_messages, remove_room

app = Flask(__name__)
app.secret_key = "sfdjkafnk"
app.config["MONGO_URI"] = "mongodb://localhost:27017/db"
db = PyMongo(app)

socketio = SocketIO(app)
login_manager = LoginManager()
login_manager.login_view = 'login'
login_manager.init_app(app)


@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


@app.route('/')
def home():
    rooms = []
    if current_user.is_authenticated:
        rooms = get_rooms_for_user(current_user.username)
        return render_template("index.html", rooms=rooms)
    else:
        return render_template("home.html")


@app.route('/login', methods=['GET', 'POST'])
def login():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    message = ''
    if request.method == 'POST':
        username = request.form.get('username')
        password_input = request.form.get('password')
        user = get_user(username)

        if user and user.check_password(password_input):
            login_user(user)
            return redirect(url_for('home'))
        else:
            message = 'Failed to login!'
    return render_template('login.html', message=message)


@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if current_user.is_authenticated:
        return redirect(url_for('home'))

    message = ''
    if request.method == 'POST':
        username = request.form.get('username')
        email = request.form.get('email')
        password = request.form.get('password')
        try:
            save_user(username, email, password)
            return redirect(url_for('login'))
        except DuplicateKeyError:
            message = "User already exists!"
    return render_template('signup.html', message=message)


@app.route("/logout/")
@login_required
def logout():
    logout_user()
    return redirect(url_for('home'))


@app.route('/create-room/', methods=['GET', 'POST'])
@login_required
def create_room():
    message = ''
    if request.method == 'POST':
        room_name = request.form.get('room_name')
        if len(room_name) == 0:
            message = "Room Name cannot be empty"
            return render_template('create_room.html', message=message)
        if len(request.form.get('members')) == 0:
            message = "Add more members"
            return render_template('create_room.html', message=message)
        if (request.form.get('members')).find(',') != -1:
            usernames = [username.strip()
                         for username in request.form.get('members').split(',')]
        else:
            usernames = [username.strip()
                         for username in request.form.get('members').split(' ')]
        if current_user.username in usernames:
            usernames.remove(current_user.username)
            if not len(usernames):
                message = "Add more members"
                return render_template('create_room.html', message=message)
        if not len(usernames):
            message = "Add more members"
            return render_template('create_room.html', message=message)
        if len(room_name) and len(usernames):
            room_id = save_room(room_name, current_user.username)

            add_room_members(room_id, room_name, usernames,
                             current_user.username)
            return redirect(url_for('view_room', room_id=room_id))
        else:
            message = "Failed to create room"
    return render_template('create_room.html', message=message)


@app.route('/rooms/<room_id>/edit', methods=['GET', 'POST'])
@login_required
def edit_room(room_id):
    room = get_room(room_id)
    if room and is_room_admin(room_id, current_user.username):
        existing_room_members = [member['_id']['username']
                                 for member in get_room_members(room_id)]
        room_members_str = ",".join(existing_room_members)
        message = ''
        if request.method == 'POST':
            room_name = request.form.get('room_name')
            if(len(request.form.get('room_name'))) == 0:
                message = "Room name cannot be empty"
                return render_template('edit_room.html', room=room, room_members_str=room_members_str, message=message)
            room['name'] = room_name
            update_room(room_id, room_name)
            if len(request.form.get('members')) == 0:
                message = "Edit unsuccessful"
                return render_template('edit_room.html', room=room, room_members_str=room_members_str, message=message)
            new_members = [username.strip()
                           for username in request.form.get('members').split(',')]
            members_to_add = list(
                set(new_members) - set(existing_room_members))
            members_to_remove = list(
                set(existing_room_members) - set(new_members))
            if current_user.username in members_to_remove:
                message = "Cannot remove admin from room"
                return render_template('edit_room.html', room=room, room_members_str=room_members_str, message=message)
            if len(members_to_add):
                add_room_members(room_id, room_name,
                                 members_to_add, current_user.username)
            if len(members_to_remove):
                remove_room_members(room_id, members_to_remove)
            message = 'Room edited successfully'
            room_members_str = ",".join(new_members)
            return redirect(url_for('view_room', room_id=room_id))

        return render_template('edit_room.html', room=room, room_members_str=room_members_str, message=message)
    else:
        message = "Not the admin for this room"
        return render_template('error.html', message=message)
    # else:
    #     return render_template('error.html')


@app.route('/rooms/<room_id>/delete-room', methods=['GET', 'POST'])
@login_required
def delete_room(room_id):
    room = get_room(room_id)
    if room and is_room_admin(room_id, current_user.username):
        remove_room(room_id)
        return redirect(url_for('home'))
    else:
        message = "Not the admin for this room"
        return render_template('error.html', message=message)


@app.route('/rooms/<room_id>/')
@login_required
def view_room(room_id):
    room = get_room(room_id)
    if room and is_room_member(room_id, current_user.username):
        room_members = get_room_members(room_id)
        messages = get_messages(room_id)
        return render_template('vr1.html', username=current_user.username, room=room, room_members=room_members,
                               messages=messages, room_id=room_id)
    # else:
    #     return render_template('error.html')


@app.route('/rooms/<room_id>/messages/')
@login_required
def get_older_messages(room_id):
    room = get_room(room_id)
    if room and is_room_member(room_id, current_user.username):
        page = int(request.args.get('page', 0))
        messages = get_messages(room_id, page)
        return dumps(messages)
    # else:
    #     return render_template('error.html')


@app.errorhandler(404)
def invalid_route(e):
    return render_template('error.html')


@socketio.on('send_message')
def handle_send_message_event(data):
    app.logger.info("{} has sent message to the room {}: {}".format(data['username'],
                                                                    data['room'],
                                                                    data['message']))
    data['created_at'] = datetime.now().strftime("%d %b, %H:%M")
    save_message(data['room'], data['message'], data['username'])
    socketio.emit('receive_message', data, room=data['room'])


@socketio.on('join_room')
def handle_join_room_event(data):
    app.logger.info("{} has joined the room {}".format(
        data['username'], data['room']))
    join_room(data['room'])
    socketio.emit('join_room_announcement', data, room=data['room'])


@socketio.on('leave_room')
def handle_leave_room_event(data):
    app.logger.info("{} has left the room {}".format(
        data['username'], data['room']))
    leave_room(data['room'])
    socketio.emit('leave_room_announcement', data, room=data['room'])


@login_manager.user_loader
def load_user(username):
    return get_user(username)


if __name__ == '__main__':
    socketio.run(app, debug=True)
