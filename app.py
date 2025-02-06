import signal
import os

import sys
from types import FrameType
from flask import Flask, jsonify, Response, request, redirect
import uuid
from sqlalchemy.dialects.postgresql import UUID
from datetime import datetime
from utils.logging import logger
from flask_sqlalchemy import SQLAlchemy
from functools import wraps
import firebase_admin
from google.cloud.sql.connector import Connector
from firebase_admin import credentials, storage, auth, initialize_app

#se tienen que agregar a las variables de entorno de cloud run DB_USER, DB_PASS, DB_NAME
app = Flask(__name__)

connector = Connector()
#agregar el archivo json de firebase para utenticar y usar este servicio
cred = credentials.Certificate("[el nombrel archivo json del proyecto de firebase]")
firebase_admin.initialize_app(cred)

def token_required(func):
    @wraps(func)
    def decorated_function(*args, **kwargs):
        header = request.headers.get("Authorization", None)
        if header:
            id_token = header.split(" ")[1]
            try:
                decoded_token = auth.verify_id_token(id_token)
            except Exception as e:
                logger.exception(e)
                return Response(status=403, response=f"Error with authentication: {e}")
        else:
            return Response(status=401, response="Missing Authorization Header")
        request.uid = decoded_token["uid"]
        return func(*args, **kwargs)

    return decorated_function

def getconn():
    user = os.getenv('DB_USER')
    password = os.getenv('DB_PASS')
    db = os.getenv('DB_NAME')

    conn = connector.connect(
        "proyecto-siniy:us-central1:siniy-2025",
        "pg8000",
        user=user,
        password=password,
        db=db,
        ip_type="public"
    )
    return conn


app.config['SQLALCHEMY_DATABASE_URI'] = "postgresql+pg8000://"
app.config['SQLALCHEMY_ENGINE_OPTIONS'] = {
    "creator": getconn
}

dbp = SQLAlchemy()
dbp.init_app(app)


# New User model based on the provided schema
class User(dbp.Model):
    __tablename__ = 'users'
    userid = dbp.Column(dbp.String(100), primary_key=True)
    username = dbp.Column(dbp.String(100), nullable=True)
    email = dbp.Column(dbp.String(100), nullable=True)
    coins = dbp.Column(dbp.Integer, nullable=True)
    lives = dbp.Column(dbp.Integer, nullable=True)
    plan = dbp.Column(dbp.Boolean, nullable=True)
    country = dbp.Column(dbp.String(100), nullable=True)


@app.route('/users', methods=['POST'])
@token_required
def create_user():
    try:
        data = request.get_json()

        new_user = User(
            userid=data['userid'],
            username=data['username'],
            email=data['email'],
            coins=data.get('coins', 0),
            lives=data.get('lives', 0),
            plan=data.get('plan', False),
            country=data.get('country', "")
        )

        dbp.session.add(new_user)
        dbp.session.commit()
        print(jsonify({'id': new_user.userid}))
        return jsonify({'id': new_user.userid}), 201
    except  Exception as e:
        print(e)


@app.route('/users/<string:userid>', methods=['GET'])
@token_required
def get_user(userid):
    user = User.query.get_or_404(userid)
    print(jsonify({
        'userid': user.userid,
        'username': user.username,
        'email': user.email,
        'coins': user.coins,
        'lives': user.lives,
        'plan': user.plan,
        'country': user.country
    }))
    return jsonify({
        'userid': user.userid,
        'username': user.username,
        'email': user.email,
        'coins': user.coins,
        'lives': user.lives,
        'plan': user.plan,
        'country': user.country
    })


@app.route('/users/<string:userid>', methods=['PUT'])
@token_required
def update_user(userid):
    user = User.query.get_or_404(userid)
    data = request.get_json()
    print("Data received:", data)

    user.username = data.get('username', user.username)
    user.email = data.get('email', user.email)
    user.coins = data.get('coins', user.coins)
    user.lives = data.get('lives', user.lives)
    user.plan = data.get('plan', user.plan)
    user.country = data.get('country', user.country)

    try:
        dbp.session.commit()
        print("User after update:", user.__dict__)
        return jsonify({'message': 'User updated successfully'})
    except Exception as e:
        dbp.session.rollback()
        print(f"Error committing changes: {e}")
        return jsonify({'message': 'Failed to update user'}), 500


@app.route('/users/check/<string:userid>', methods=['GET'])
@token_required
def check_user_exists(userid):
    user_exists = User.query.filter_by(userid=userid).first() is not None

    print(jsonify({'exists': user_exists}))
    return jsonify({'exists': user_exists})


@app.route("/")
def hello() -> str:
    logger.info("Child logger with trace Id.")
    return redirect("https://kidtales.app")


def shutdown_handler(signal_int: int, frame: FrameType) -> None:
    logger.info(f"Caught Signal {signal.strsignal(signal_int)}")

    from utils.logging import flush

    flush()

    sys.exit(0)

if __name__ == "__main__":
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port)
else:
    # handles Cloud Run container termination
    signal.signal(signal.SIGTERM, shutdown_handler)