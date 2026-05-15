@echo off
:: Investment Research App — manual launcher (for CMD use)
:: For silent desktop launch use launch.vbs instead

wsl bash -c "pgrep -f 'streamlit run app.py' > /dev/null 2>&1 || (cd /home/hchxie/projects/investment-agents && nohup python3 -m streamlit run app.py >> /tmp/streamlit_app.log 2>&1 &)"
timeout /t 5 /nobreak > nul
start http://localhost:8501
