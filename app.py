import streamlit as st
import pandas as pd
import numpy as np
import requests
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# Page configuration
st.set_page_config(page_title="World Cup Predictor", page_icon="⚽", layout="centered")

API_KEY = "fca580857f6cf30156ef0e1526082430"
SPREADSHEET_NAME = "WorldCupPredictions"  # ודא שזה בדיוק השם של קובץ ה-Sheets שלך

# --- Google Sheets Connection Logic ---
@st.cache_resource
def init_sheets():
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
        client = gspread.authorize(creds)
        sheet = client.open(SPREADSHEET_NAME).sheet1
        return sheet
    except Exception as e:
        st.error(f"Error connecting to Google Sheets: {e}")
        return None

sheet = init_sheets()

# פונקציה לשליפת כל הניחושים הקיימים בטבלה
def load_all_predictions(sheet_obj):
    if sheet_obj is None:
        return {}
    try:
        records = sheet_obj.get_all_records()
        preds = {}
        for r in records:
            m_id = str(r.get('Match_ID'))
            player = str(r.get('Player'))
            p_home = r.get('Pred_Home')
            p_away = r.get('Pred_Away')
            
            if m_id not in preds:
                preds[m_id] = {}
            preds[m_id][player] = (int(p_home), int(p_away))
        return preds
    except Exception as e:
        st.error(f"Error loading predictions from Sheets: {e}")
        return {}

# פונקציה לשמירה או עדכון של ניחוש בטבלה
def save_prediction_to_sheet(sheet_obj, match_id, player, pred_home, pred_away):
    if sheet_obj is None:
        return
    try:
        records = sheet_obj.get_all_records()
        row_to_update = None
        
        for idx, r in enumerate(records):
            if str(r.get('Match_ID')) == str(match_id) and str(r.get('Player')) == str(player):
                row_to_update = idx + 2  # +1 לכותרות, +1 לאינדקס גוגל (מתחיל מ-1)
                break
                
        if row_to_update:
            sheet_obj.update_cell(row_to_update, 3, int(pred_home))
            sheet_obj.update_cell(row_to_update, 4, int(pred_away))
        else:
            sheet_obj.append_row([str(match_id), str(player), int(pred_home), int(pred_away)])
        st.success(f"Prediction for {player} saved successfully!")
    except Exception as e:
        st.error(f"Error saving prediction: {e}")

# טעינת הניחושים הקיימים מהענן
all_db_preds = load_all_predictions(sheet)

# --- API Football Fetching Logic with Cache ---
@st.cache_data(ttl=60) 
def get_live_fixtures():
    url = "https://v3.football.api-sports.io/fixtures"
    querystring = {"league": "1", "season": "2026"}
    headers = {
        "x-apisports-key": API_KEY,
        "x-apisports-host": "v3.football.api-sports.io"
    }
    try:
        response = requests.get(url, headers=headers, params=querystring)
        data = response.json()
        if 'errors' in data and data['errors']:
            st.error(f"API Error message: {data['errors']}")
            return []
        matches_list = data.get('response', [])
        if matches_list:
            matches_list.sort(key=lambda x: x['fixture']['timestamp'])
        return matches_list
    except Exception as e:
        st.error(f"Connection Error: {e}")
        return []

api_matches = get_live_fixtures()

# רשימת 9 השחקנים הרשמית שלכם וניקוד הבסיס שלהם
current_user = "Yuvi20"
all_players = ["King Levi", "Ballal1", "Dani uretsky", "King Adir", "King Sag", "Agadi1997", "Shmuelshoan", "Yuvi20", "BlancoChif"]
baseline_points = {
    "King Levi": 225, "Ballal1": 215, "Dani uretsky": 205,
    "King Adir": 200, "King Sag": 190, "Agadi1997": 175,
    "Shmuelshoan": 165, "Yuvi20": 145, "BlancoChif": 140
}

# --- Parsing API Matches ---
matches = []
if not api_matches:
    st.info("No matches loaded yet. Waiting for API...")
else:
    for am in api_matches:
        m_id = str(am['fixture']['id'])
        status_short = am['fixture']['status']['short']
        is_live = status_short in ['1H', 'HT', '2H', 'ET', 'P', 'LIVE']
        is_finished = status_short in ['FT', 'AET', 'PEN']
        
        status_display = "LIVE" if is_live else ("Finished" if is_finished else "Upcoming")
        
        match_time_utc = pd.to_datetime(am['fixture']['date'])
        match_time_il = match_time_utc.tz_convert('Asia/Jerusalem')
        formatted_time = match_time_il.strftime('%d/%m/%Y %H:%M')
        
        # משיכת ניחושים אמיתיים מהטבלה עבור המשחק הספציפי הזה
        match_preds = all_db_preds.get(m_id, {})
        
        # שליפת הניחוש של המשתמש הנוכחי (ברירת מחדל 0 אם לא קיים)
        my_saved_pred = match_preds.get(current_user, (0, 0))
            
        matches.append({
            "id": m_id,
            "home": am['teams']['home']['name'],
            "away": am['teams']['away']['name'],
            "status": status_display,
            "date_str": formatted_time,
            "live_home": am['goals']['home'] if am['goals']['home'] is not None else 0,
            "live_away": am['goals']['away'] if am['goals']['away'] is not None else 0,
            "my_pred_home": my_saved_pred[0],
            "my_pred_away": my_saved_pred[1],
            "all_preds": match_preds
        })

# Exact FIFA Scoring Logic (Max 30 points)
def calc_points(pred_h, pred_a, actual_h, actual_a):
    if pred_h is None or pred_a is None: return 0
    pts = 0
    p_sign = np.sign(pred_h - pred_a)
    a_sign = np.sign(actual_h - actual_a)
    
    if p_sign == a_sign: pts += 10
    if pred_h == actual_h: pts += 5
    if pred_a == actual_a: pts += 5
    if (pred_h - pred_a) == (actual_h - actual_a): pts += 5
    if pred_h == actual_h and pred_a == actual_a: pts += 5
    
    return pts

# Tabs Definition
tab1, tab2 = st.tabs(["My Predictions", "Live Table"])

with tab1:
    st.markdown("## My Predictions")
    
    # שינוי משתמש לצורכי בדיקה בממשק
    selected_user = st.selectbox("Log in as:", all_players, index=all_players.index(current_user))
    
    for m in matches: 
        is_live_or_finished = m["status"] in ["LIVE", "Finished"]
        m_id = m["id"]
        
        with st.container():
            st.markdown(f"#### {m['home']} vs {m['away']} - {m['status']}")
            st.caption(f"🕒 {m['date_str']} (Israel Time)")
            
            if m["status"] == "LIVE":
                st.markdown(f"<h3 style='color:#ff4b4b;'>Live Score: {m['live_home']} - {m['live_away']}</h3>", unsafe_allow_html=True)
            elif m["status"] == "Finished":
                st.markdown(f"**Final Score: {m['live_home']} - {m['live_away']}**")
            else:
                st.markdown(f"**Match hasn't started yet**")
            
            # שליפת ניחוש קיים עבור המשתמש הנבחר
            current_pred = m["all_preds"].get(selected_user, (0, 0))
            
            col1, col2 = st.columns(2)
            with col1:
                input_home = st.number_input(f"{m['home']} (Prediction)", value=current_pred[0], disabled=is_live_or_finished, key=f"h_{m_id}_{selected_user}", min_value=0)
            with col2:
                input_away = st.number_input(f"{m['away']} (Prediction)", value=current_pred[1], disabled=is_live_or_finished, key=f"a_{m_id}_{selected_user}", min_value=0)
            
            # כפתור שמירה ייעודי למשחקים עתידיים
            if not is_live_or_finished:
                if st.button("Save Prediction 💾", key=f"btn_{m_id}_{selected_user}"):
                    save_prediction_to_sheet(sheet, m_id, selected_user, input_home, input_away)
                    st.rerun()
            
            if is_live_or_finished:
                with st.expander("View All Players' Predictions"):
                    preds_data = []
                    for player in all_players:
                        p_tuple = m["all_preds"].get(player, None)
                        if p_tuple:
                            pts = calc_points(p_tuple[0], p_tuple[1], m['live_home'], m['live_away'])
                            pred_str = f"{p_tuple[0]} - {p_tuple[1]}"
                        else:
                            pts = 0
                            pred_str = "No prediction"
                        preds_data.append({"Player": player, "Prediction": pred_str, "Points Earned": f"+{pts}"})
                    
                    st.dataframe(pd.DataFrame(preds_data), hide_index=True, use_container_width=True)
            st.markdown("---")

with tab2:
    st.markdown("## Live Table")
    
    if len(matches) > 0:
        table_data = []
        
        # חישוב הניקוד המצטבר של כל שחקן על בסיס כל משחקי העבר והלייב בטורניר
        for player in all_players:
            total_earned = 0
            base_pts = baseline_points.get(player, 0)
            
            for m in matches:
                if m["status"] in ["LIVE", "Finished"]:
                    p_tuple = m["all_preds"].get(player, None)
                    if p_tuple:
                        total_earned += calc_points(p_tuple[0], p_tuple[1], m['live_home'], m['live_away'])
            
            table_data.append({
                "Player": player,
                "Base Pts": base_pts,
                "Added": total_earned,
                "Total Pts": base_pts + total_earned
            })
            
        df = pd.DataFrame(table_data)
        df['Base Rank'] = df['Base Pts'].rank(method='min', ascending=False)
        df['New Rank'] = df['Total Pts'].rank(method='min', ascending=False)
        
        def get_trend(row):
            if row['New Rank'] < row['Base Rank']: return "⬆️"
            elif row['New Rank'] > row['Base Rank']: return "⬇️"
            else: return "➖"
            
        df['Trend'] = df.apply(get_trend, axis=1)
        df = df.sort_values("New Rank").reset_index(drop=True)
        
        display_df = pd.DataFrame({
            "Rank": df['New Rank'].astype(int),
            "Display Name": df['Player'],
            "Total Pts": df['Total Pts'],
            "Added Pts": "+" + df['Added'].astype(str),
            "Trend": df['Trend']
        })
        
        st.dataframe(display_df, hide_index=True, use_container_width=True)
    else:
        st.write("Table will update once a match starts.")