#静音恢复
import os, json, time, tempfile, requests, configparser
from datetime import datetime
import obspython as obs

# ============================================
# 可配置参数
# ============================================
T = 300                           # 必须与静音宏一致
DEBUG = ${Debug}
WEBHOOK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=${BotKey}"
STATE_FILE = os.path.join(tempfile.gettempdir(), "mute_time.json")
# 恢复宏不需要截图路径，但保留参数以保持一致性
SCREENSHOT_FOLDER = ""           

# ============================================
# 全局变量
# ============================================
last_log_time = 0
last_read_time = 0
cached_state = None

def log_info(msg):
    if DEBUG:
        obs.script_log(obs.LOG_INFO, msg)

def log_warning(msg):
    if DEBUG:  # 加上DEBUG控制
        obs.script_log(obs.LOG_WARNING, msg)

def format_time(seconds):
    minutes = int(seconds / 60)
    secs = int(seconds % 60)
    if minutes > 0:
        return f"{minutes}分{secs}秒"
    else:
        return f"{secs}秒"

def send_webhook(content):
    try:
        payload = {
            "msgtype": "text",
            "text": {"content": content}
        }
        requests.post(WEBHOOK, headers={"Content-Type": "application/json"},
                     data=json.dumps(payload), timeout=5)
    except:
        pass

def read_state():
    global last_read_time, cached_state
    now = time.time()
    if cached_state is not None and now - last_read_time < 1:
        return cached_state
    try:
        with open(STATE_FILE, 'r') as f:
            cached_state = json.load(f)
        last_read_time = now
        return cached_state
    except:
        return None

def run():
    global last_log_time, cached_state
    now = datetime.now()
    current_time = time.time()
    time_str = now.strftime("%H:%M:%S")
    
    log_info(f"[{time_str}] ===== 恢复宏被触发 =====")
    
    state = read_state()
    
    if state:
        mute_start = state.get("mute_start")
        notified = state.get("notified", False)
        total_seconds = max(0, int(current_time - mute_start))
        
        if notified or total_seconds >= T:
            msg = f"🔊 声音已恢复，本次静音持续 {format_time(total_seconds)}"
            log_warning(f"[{time_str}] {msg}")
            send_webhook(msg)
        
        # 删除状态文件
        try:
            os.remove(STATE_FILE)
            cached_state = None
        except:
            pass
    else:
        if current_time - last_log_time > 60:
            log_info(f"[{time_str}] 没有状态文件")
            last_log_time = current_time
    
    return True

def script_description():
    return "静音恢复"

def script_load(settings):
    run()

def script_unload():
    pass
