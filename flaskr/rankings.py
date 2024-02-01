import functools
import pandas as pd
import sqlalchemy

from flask import (
    Blueprint, flash, g, redirect, render_template, request, session, url_for
)

from flaskr.db import get_db

bp = Blueprint('rankings', __name__, url_prefix='/rankings')

@bp.route('/', methods = ["GET"])
def rankings():
    db = get_db()
    rankings = db.execute(
            'SELECT ID, Team, Ranking, Diff'
            ' FROM rankings'
            ' ORDER BY id ASC'
    ).fetchall()
    return render_template('rankings/rankings.html', rankings = rankings)
