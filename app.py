import streamlit as st
import pandas as pd
import numpy as np
import requests
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# Page configuration
st.set_page_config(page_title="World Cup Predictor", page_icon="⚽", layout="centered")

API_KEY = "fca580857f6cf30156ef0e1526082430"
SPREADSHEET_NAME = "WorldCupPredictions"

# --- Google Sheets Connection Logic (Using Secrets) ---
@st.cache_resource
def init_sheets():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        # קריאה מתוך ה-Secrets שהגדרנו בסטרימליט
        creds_dict = st.secrets["connections"]["gspread"]["gspread_credentials"]
        creds_json = json.loads(creds_dict)
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_json, scope)
        client = gspread.authorize(creds)
        sheet = client.open(SPREADSHEET_NAME).sheet1
        return sheet
    except Exception as e:
        st.error(f"Error connecting to Google Sheets: {e}")
        return None

sheet = init_sheets()

# פונקציה לשליפת כל הניחושים הקיימים בטבלה
def load_all_predictions(sheet_obj):
    if sheet_obj is None: return {}
    try:
        records = sheet_obj.get_all_records()
        preds = {}
        for r in records:
            m_id = str(r.get('Match_ID'))
            player = str(r.get('Player'))
            p_home = r.get('Pred_Home')
            p_away = r.get('Pred_Away')
            if m_id not in preds: preds[m_id] = {}
            preds[m_id][player] = (int(p_home), int(p_away))
        return preds
    except Exception: return {}

# פונקציה לשמירה בטבלה
def save_prediction_to_sheet(sheet_obj, match_id, player, pred_home, pred_away):
    if sheet_obj is None: return
    try:
        records = sheet_obj.get_all_records()
        row_to_update = None
        for idx, r in enumerate(records):
            if str(r.get('Match_ID')) == str(match_id) and str(r.get('Player')) == str(player):
                row_to_update = idx + 2
                break
        if row_to_update:
            sheet_obj.update_cell(row_to_update, 3, int(pred_home))
            sheet_obj.update_cell(row_to_update, 4, int(pred_away))
        else:
            sheet_obj.append_row([str(match_id), str(player), int(pred_home), int(pred_away)])
        st.success(f"Prediction saved!")
    except Exception as e:
        st.error(f"Error saving: {e}")

all_db_preds = load_all_predictions(sheet)

# --- API Football Fetching ---
@st.cache_data(ttl=60) 
def get_live_fixtures():
    url = "https://v3.football.api-sports.io/fixtures"
    querystring = {"league": "1", "season": "2026"}
    headers = {"x-apisports-key": API_KEY, "x-apisports-host": "v3.football.api-sports.io"}
    try:
        response = requests.get(url, headers=headers, params=querystring)
        data = response.json()
        matches_list = data.get('response', [])
        if matches_list: matches_list.sort(key=lambda x: x['fixture']['timestamp'])
        return matches_list
    except: return []

api_matches = get_live_fixtures()
all_players = ["King Levi", "Ballal1", "Dani uretsky", "King Adir", "King Sag", "Agadi1997", "Shmuelshoan", "Yuvi20", "BlancoChif"]
baseline_points = {"King Levi": 225, "Ballal1": 215, "Dani uretsky": 205, "King Adir": 200, "King Sag": 190, "Agadi1997": 175, "Shmuelshoan": 165, "Yuvi20": 145, "BlancoChif": 140}

matches = []
for am in api_matches:
    m_id = str(am['fixture']['id'])
    is_live = am['fixture']['status']['short'] in ['1H', 'HT', '2H', 'ET', 'P', 'LIVE']
    is_finished = am['fixture']['status']['short'] in ['FT', 'AET', 'PEN']
    status_display = "LIVE" if is_live else ("Finished" if is_finished else "Upcoming")
    
    match_time_il = pd.to_datetime(am['fixture']['date']).tz_convert('Asia/Jerusalem').strftime('%d/%m/%Y %H:%M')
    
    matches.append({
        "id": m_id, "home": am['teams']['home']['name'], "away": am['teams']['away']['name'],
        "status": status_display, "date_str": match_time_il,
        "live_home": am['goals']['home'] or 0, "live_away": am['goals']['away'] or 0,
        "all_preds": all_db_preds.get(m_id, {})
    })

def calc_points(pred_h, pred_a, actual_h, actual_a):
    if pred_h is None or pred_a is None: return 0
    pts = 0
    if np.sign(pred_h - pred_a) == np.sign(actual_h - actual_a): pts += 10
    if pred_h == actual_h: pts += 5
    if pred_a == actual_a: pts += 5
    if (pred_h - pred_a) == (actual_h - actual_a): pts += 5
    if pred_h == actual_h and pred_a == actual_a: pts += 5
    return pts

tab1, tab2 = st.tabs(["My Predictions", "Live Table"])

with tab1:
    selected_user = st.selectbox("Log in as:", all_players)
    for m in matches: 
        is_live_or_finished = m["status"] in ["LIVE", "Finished"]
        current_pred = m["all_preds"].get(selected_user, (0, 0))
        with st.container():
            st.markdown(f"#### {m['home']} vs {m['away']} - {m['status']}")
            st.caption(f"🕒 {m['date_str']} (Israel Time)")
            if m["status"] == "LIVE": st.markdown(f"### Live: {m['live_home']} - {m['live_away']}")
            elif m["status"] == "Finished": st.markdown(f"**Final: {m['live_home']} - {m['live_away']}**")
            
            c1, c2 = st.columns(2)
            ph = c1.number_input(f"{m['home']}", value=current_pred[0], disabled=is_live_or_finished, key=f"h_{m['id']}_{selected_user}")
            pa = c2.number_input(f"{m['away']}", value=current_pred[1], disabled=is_live_or_finished, key=f"a_{m['id']}_{selected_user}")
            
            if not is_live_or_finished and st.button("Save 💾", key=f"btn_{m['id']}_{selected_user}"):
                save_prediction_to_sheet(sheet, m['id'], selected_user, ph, pa)
                st.rerun()
            st.markdown("---")

with tab2:
    st.markdown("## Live Table")
    table_data = []
    for player in all_players:
        total = baseline_points.get(player, 0) + sum(calc_points(*m["all_preds"].get(player, (0,0)), m['live_home'], m['live_away']) for m in matches if m["status"] in ["LIVE", "Finished"])
        table_data.append({"Player": player, "Total Pts": total})
    st.dataframe(pd.DataFrame(table_data).sort_values("Total Pts", ascending=False), hide_index=True)