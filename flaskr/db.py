import sqlite3
import pandas as pd
import click
from flask import current_app, g
import requests
from bs4 import BeautifulSoup
from time import sleep
from IPython.display import clear_output
from IPython.display import display, HTML
from datetime import datetime, timedelta, date
import numpy as np

def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(
            current_app.config['DATABASE'],
            detect_types=sqlite3.PARSE_DECLTYPES
        )
        g.db.row_factory = sqlite3.Row

    return g.db


def close_db(e=None):
    db = g.pop('db', None)

    if db is not None:
        db.close()

def getWebsite(url):
    sleep(5)
    page = requests.get(url)
    soup = BeautifulSoup(page.content, "html.parser")
    return soup

def getDayPage(month, day, year):
    url = f"https://www.sports-reference.com/cbb/boxscores/index.cgi?month={month}&day={day}&year={year}"
    return getWebsite(url)

def getGamesOnPage(soup, time):
    games = soup.find_all("div", class_ = "game_summary nohover gender-m")
    gameList = []
    for game in games:
        gameDict = {}
        teams = game.find_all("tr")
        awayRows = teams[0].find_all("td")
        gameDict["Away"] = awayRows[0].find("a").text
        gameDict["AwayScore"] = awayRows[1].text
        homeRows = teams[1].find_all("td")
        gameDict["Home"] = homeRows[0].find("a").text
        gameDict["HomeScore"] = homeRows[1].text
        gameDict["Time"] = time
        gameList.append(gameDict)
    return gameList

def get_games(conn):
    games = pd.read_sql("""SELECT Home, Away, HomeScore, AwayScore, Time FROM
    games""", conn)
    if games.empty:
        i = 0
    else:
        i = int(games['Time'].max() + 1)
    currentDate = datetime.now().date()
    firstDate = datetime(2023, 11, 6).date()
    while True:
        newDate = firstDate + timedelta(days = i)
        #print("HI")
        print(newDate)
        if newDate.month == currentDate.month and newDate.day == currentDate.day and newDate.year == currentDate.year:
            break
        clear_output(wait=True)
        print(f"{round(i * 100 / (currentDate - firstDate).days, 2)}%")
        gameList = getGamesOnPage(getDayPage(newDate.month, newDate.day, newDate.year), i)
        #print(gameList)
        new_data = pd.DataFrame(gameList)
        games = pd.concat([games, new_data], ignore_index = True)
        i+=1
    games['HomeScore'].replace('', np.nan, inplace=True)
    games = games.dropna()
    games = games.drop_duplicates()
    games.to_sql(name='games', con=conn, if_exists='replace', index=False)
    return games

def getDiffs(rankings, oldRankings):
    diffs = []
    for index, row in rankings.iterrows():
        try:
            oldIndex = oldRankings.index[oldRankings['Team'] == row['Team']].tolist()[0]
        except:
            oldIndex = index
        if oldIndex == index:
            toAdd = "="
        elif oldIndex > index:
            toAdd = f"+{(oldIndex - index)}"
        else:
            toAdd = f"-{(index - oldIndex)}"
        diffs.append(toAdd)
    return diffs

def update_rankings(conn):
    cur = conn.cursor()
    cur.execute('SELECT * FROM updatedDate')
    oldDate = cur.fetchone()
    curDate = str((datetime.now() - timedelta(hours = 9)).day)
    print(curDate)
    if oldDate == None or curDate != oldDate[0]:
        if oldDate == None:
            conn.execute('INSERT INTO updatedDate VALUES(?)',
                    (curDate,))
        else:
            conn.execute('UPDATE updatedDate SET updatedDate=?', (curDate,))
        games = pd.read_sql("""SELECT Home, Away, HomeScore, 
                AwayScore, Time FROM games""", conn)
        games['HomeScore'] = games['HomeScore'].astype(int)
        games['AwayScore'] = games['AwayScore'].astype(int)
        games['Time'] = games['Time'].astype(int)
        teams = []
        #print(games)
        for index, row in games.iterrows():
            if not row["Home"] in teams:
                teams.append(row["Home"])
        games = games[games['Home'].isin(teams) & games['Away'].isin(teams)]
        rankings = runRankings(games, teams, conn)
        rankings.to_sql(name='rankings', con=conn, if_exists='replace', index=False)

def runRankings(games, teams, conn):
    adjTimes = (games['Time']) / games['Time'].max() / 10 + 0.95
    #print(adjTimes)
    games['Margin'] = ((games['HomeScore'] - games['AwayScore']) / (games['HomeScore'] 
        + games['AwayScore']) - 0.01) * adjTimes
    #display(games)
    label = np.array(games['Margin'])
    df = pd.DataFrame(columns = teams)
    newRows = []
    for index, row in games.iterrows():
        newRows.append({row['Home']:1, row['Away']:-1})
    df = pd.concat([df, pd.DataFrame(newRows)], ignore_index = True)
    df = df.fillna(0)
    df = df.sort_index(axis=1)
    data = np.array(df)
    o = data
    y = label

    n = o.shape[0]
    d = o.shape[1]
    w = np.zeros((d,1))
    y = np.reshape(y, (n,1))

    step = 0.01
    err_list = []
    o = np.nan_to_num(o)
    y = np.nan_to_num(y)
    runs = 2000
    for i in range(runs):
        der = o.T.dot(o.dot(w) - y)
        w = w - step * der

        err = (o.dot(w) - y)
        mse = (err.T.dot(err)/n).item()
        err_list.append(mse)
        if i % (runs/20) == 0:
            clear_output(wait=True)
            print(f"{round(i * 100 / runs, 2)}%")

    rankings = pd.DataFrame(columns = ['ID', 'Team', 'Ranking', 'Diff'])
    rankings['Team'] = sorted(teams)
    rankings['Ranking'] = w
    rankings = rankings.sort_values(by = 'Ranking', ascending = False)
    rankings = rankings.reset_index(drop = True)
    rankings['ID'] = rankings.index + 1

    oldRankings = pd.read_sql("""SELECT ID, Team, Ranking, Diff FROM rankings""",
            conn)
    rankings['Diff'] = getDiffs(rankings, oldRankings)
    return rankings

def init_db():
    db = get_db()
    with current_app.open_resource('schema.sql') as f:
        db.executescript(f.read().decode('utf8'))
    update_db()

def update_db():
    conn = get_db()
    cur = conn.cursor()
    gamesdf = get_games(conn)
    update_rankings(conn)
    close_db()

@click.command('init-db')
def init_db_command():
    """Clear the existing data and create new tables."""
    init_db()
    click.echo('Initialized the database.')

def init_app(app):
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
