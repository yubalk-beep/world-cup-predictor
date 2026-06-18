import streamlit as st
import pandas as pd
import numpy as np
import requests
import gspread
import json
from oauth2client.service_account import ServiceAccountCredentials

# Page configuration
st.set_page_config(page_title="World Cup Predictor", page_icon="⚽", layout="centered")

# --- CSS עיצוב ---
st.markdown("""
    <style>
    .match-card { background-color: #f8f9fa; padding: 20px; border-radius: 15px; margin-bottom: 20px; border-left: 6px solid #ff4b4b; box-shadow: 2px 2px 10px rgba(0,0,0,0.1); }
    .round-header { background-color: #1e3a8a; color: white; padding: 15px; border-radius: 8px; margin-top: 40px; margin-bottom: 20px; text-align: center; font-weight: bold; }
    .predictions-box { background-color: #ffffff; border: 2px solid #1e3a8a; border-radius: 10px; padding: 15px; margin-top: 10px; box-shadow: 3px 3px 15px rgba(30, 58, 138, 0.2); }
    </style>
    """, unsafe_allow_html=True)

SPREADSHEET_NAME = "WorldCupPredictions"

# --- Google Sheets Connection ---
@st.cache_resource
def init_sheets():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
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

def load_all_predictions(sheet_obj):
    if sheet_obj is None: return {}
    try:
        records = sheet_obj.get_all_records()
        preds = {}
        for r in records:
            m_id = str(r.get('Match_ID'))
            if m_id not in preds: preds[m_id] = {}
            preds[m_id][str(r.get('Player'))] = (int(r.get('Pred_Home')), int(r.get('Pred_Away')))
        return preds
    except Exception: return {}

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
        st.success("Prediction saved!")
    except Exception as e:
        st.error(f"Error saving: {e}")

all_db_preds = load_all_predictions(sheet)

# --- API Data ---
@st.cache_data(ttl=60) 
def get_live_fixtures():
    headers = {"x-apisports-key": "fca580857f6cf30156ef0e1526082430", "x-apisports-host": "v3.football.api-sports.io"}
    response = requests.get("https://v3.football.api-sports.io/fixtures", headers=headers, params={"league": "1", "season": "2026"}).json()
    matches_list = response.get('response', [])
    if matches_list: matches_list.sort(key=lambda x: x['fixture']['timestamp'])
    return matches_list

api_matches = get_live_fixtures()
all_players = ["King Levi", "Ballal1", "Dani uretsky", "King Adir", "King Sag", "Agadi1997", "Shmuelshoan", "Yuvi20", "BlancoChif"]
baseline_points = {"King Levi": 250, "King Sag": 245, "Ballal1": 245, "King Adir": 240, "Dani uretsky": 230, "Agadi1997": 225, "Shmuelshoan": 220, "Yuvi20": 185, "BlancoChif": 170}

matches = []
for am in api_matches:
    date_dt = pd.to_datetime(am['fixture']['date']).tz_convert('Asia/Jerusalem')
    matches.append({
        "id": str(am['fixture']['id']),
        "round": am['league']['round'],
        "home": am['teams']['home']['name'],
        "away": am['teams']['away']['name'],
        "day": date_dt.strftime('%A'),
        "date_str": date_dt.strftime('%d/%m/%Y %H:%M'),
        "status": "LIVE" if am['fixture']['status']['short'] in ['1H', '2H', 'LIVE'] else ("Finished" if am['fixture']['status']['short'] in ['FT', 'AET', 'PEN'] else "Upcoming"),
        "live_h": am['goals']['home'] or 0, "live_a": am['goals']['away'] or 0,
        "all_preds": all_db_preds.get(str(am['fixture']['id']), {})
    })

def calc_points(ph, pa, ah, aa):
    if ph is None or pa is None: return 0
    pts = 0
    if np.sign(ph - pa) == np.sign(ah - aa): pts += 10
    if ph == ah: pts += 5
    if pa == aa: pts += 5
    if (ph - pa) == (ah - aa): pts += 5
    if ph == ah and pa == aa: pts += 5
    return pts

# --- UI ---
tab1, tab2 = st.tabs(["⚽ My Predictions", "📊 Live Table"])

with tab1:
    selected_user = st.selectbox("Select Player:", all_players)
    current_round = ""
    for m in matches:
        if m['round'] != current_round:
            current_round = m['round']
            st.markdown(f'<div class="round-header">Round: {current_round}</div>', unsafe_allow_html=True)
        
        is_locked = m["status"] != "Upcoming"
        p = m["all_preds"].get(selected_user, (0, 0))
        
        st.markdown(f'''<div class="match-card">
            <b>{m['day']} | {m['date_str']}</b><br>
            <h4>{m['home']} vs {m['away']}</h4>
            Status: <b>{m['status']}</b><br>
            Score: {m['live_h']} - {m['live_a']}
            </div>''', unsafe_allow_html=True)
            
        c1, c2 = st.columns(2)
        ph = c1.number_input(f"{m['home']}", value=int(p[0]), disabled=is_locked, key=f"h_{m['id']}_{selected_user}")
        pa = c2.number_input(f"{m['away']}", value=int(p[1]), disabled=is_locked, key=f"a_{m['id']}_{selected_user}")
        
        if not is_locked and st.button("Save 💾", key=f"btn_{m['id']}_{selected_user}"):
            save_prediction_to_sheet(sheet, m['id'], selected_user, ph, pa)
            st.rerun()
            
        if is_locked:
            st.markdown('<div class="predictions-box">', unsafe_allow_html=True)
            st.markdown("<b>👥 All Predictions:</b>", unsafe_allow_html=True)
            data = [{"Player": pl, "Prediction": f"{m['all_preds'].get(pl, 'Unsubmitted')}"} for pl in all_players]
            st.table(pd.DataFrame(data))
            st.markdown('</div>', unsafe_allow_html=True)

with tab2:
    st.markdown("## 📊 League Standings")
    table_data = []
    for p in all_players:
        earned = sum(calc_points(*m["all_preds"].get(p, (0,0)), m['live_h'], m['live_a']) for m in matches if m["status"] in ["LIVE", "Finished"] and p in m["all_preds"])
        table_data.append({"Player": p, "Total Pts": baseline_points.get(p, 0) + earned})
    st.dataframe(pd.DataFrame(table_data).sort_values("Total Pts", ascending=False), hide_index=True, use_container_width=True)