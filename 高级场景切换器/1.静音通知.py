#静音通知
import os, json, time, tempfile, requests, glob, base64, hashlib, configparser
from datetime import datetime
import obspython as obs

# ============================================
# 可配置参数
# ============================================
T = 300                           # 静音阈值(秒)
DEBUG = ${Debug}
WEBHOOK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=${BotKey}"
STATE_FILE = os.path.join(tempfile.gettempdir(), "mute_time.json")
SCREENSHOT_FOLDER = ""           # 为空则自动获取OBS录制路径
TEXT_IMG_DELAY = 1               # 文字和图片发送间隔(秒)

# ============================================
# 全局变量
# ============================================
last_read_time = 0
last_write_time = 0
cached_state = None
cached_folder = ""               # 缓存的截图文件夹路径

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

def get_screenshot_folder():
    """获取截图文件夹路径（带缓存）"""
    global cached_folder
    
    # 如果已手动设置，直接返回
    if SCREENSHOT_FOLDER:
        return SCREENSHOT_FOLDER
    
    # 如果已有缓存，直接返回
    if cached_folder:
        return cached_folder
    
    # 自动获取OBS录制路径
    try:
        basic_ini = os.path.join(
            os.environ.get('APPDATA', ''),
            "obs-studio", "basic", "profiles", "未命名", "basic.ini"
        )
        
        if os.path.exists(basic_ini):
            config = configparser.ConfigParser()
            config.read(basic_ini, encoding='utf-8-sig')
            
            # 获取输出模式
            output_mode = config.get('Output', 'Mode', fallback='Simple')
            
            if output_mode == 'Simple':
                record_path = config.get('SimpleOutput', 'FilePath', fallback='')
            else:
                record_path = config.get('AdvOut', 'RecFilePath', fallback='')
            
            if record_path:
                cached_folder = record_path
                log_info(f"自动获取录制路径: {cached_folder}")
                return cached_folder
    except Exception as e:
        log_info(f"获取录制路径失败: {e}")
    
    # 默认使用用户视频目录
    cached_folder = os.path.join(os.path.expanduser("~"), "Videos")
    log_info(f"使用默认路径: {cached_folder}")
    return cached_folder

def send_abnormal_screenshot():
    """发送异常截图"""
    folder = get_screenshot_folder()
    
    try:
        files = [(os.path.getmtime(f), f) for f in glob.glob(os.path.join(folder, "Screenshot*.png"))]
        if not files:
            log_info("未找到截图文件")
            return False, ""
        
        latest_file = max(files)[1]
        filename = os.path.basename(latest_file)
        log_info(f"找到最新截图: {filename}")
        
        with open(latest_file, "rb") as f:
            img = f.read()
        
        # 图片说明
        caption = f"⚠️异常{datetime.now().strftime('%H:%M:%S')}"
        
        # 发图片
        img_payload = {
            "msgtype": "image",
            "image": {
                "base64": base64.b64encode(img).decode(),
                "md5": hashlib.md5(img).hexdigest()
            }
        }
        
        response = requests.post(
            WEBHOOK,
            headers={"Content-Type": "application/json"},
            data=json.dumps(img_payload),
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            if result.get("errcode") == 0:
                log_warning("异常截图发送成功")
                return True, caption
            else:
                log_warning(f"异常截图发送失败: {result}")
        else:
            log_warning(f"异常截图HTTP错误: {response.status_code}")
            
    except Exception as e:
        log_warning(f"发送截图异常: {e}")
    
    return False, ""

def send_text_webhook(content):
    """发送文本消息"""
    try:
        payload = {
            "msgtype": "text",
            "text": {"content": content}
        }
        
        response = requests.post(
            WEBHOOK,
            headers={"Content-Type": "application/json"},
            data=json.dumps(payload),
            timeout=5
        )
        
        if response.status_code == 200:
            log_warning(f"文本发送成功")
            return True
    except Exception as e:
        log_warning(f"文本发送异常: {e}")
    return False

def send_abnormal_notification(msg):
    """发送异常通知：先发图片，再发合并文字"""
    # 先发图片，获取图片说明
    success, caption = send_abnormal_screenshot()
    
    # 等待设置的时间
    time.sleep(TEXT_IMG_DELAY)
    
    # 发合并后的文字（静音提醒 + 图片说明）
    if success:
        combined_msg = f"{msg}（{caption}）"
    else:
        combined_msg = msg
    
    send_text_webhook(combined_msg)

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

def write_state(state):
    global last_write_time, cached_state
    now = time.time()
    
    cached_state = state
    
    if now - last_write_time < 1:
        return True
    
    try:
        with open(STATE_FILE, 'w') as f:
            json.dump(state, f)
        last_write_time = now
        return True
    except:
        return False

def run():
    now = datetime.now()
    current_time = time.time()
    time_str = now.strftime("%H:%M:%S")
    
    log_info(f"[{time_str}] ===== 静音宏被触发 =====")
    
    # 静音检测逻辑
    state = read_state()
    if state:
        mute_start = state.get("mute_start")
        last_notify = state.get("last_notify")
        notified = state.get("notified", False)
    else:
        mute_start = None
        last_notify = None
        notified = False
    
    if mute_start is None:
        mute_start = current_time
        last_notify = mute_start
        notified = False
        log_warning(f"[{time_str}] 静音开始")
    
    total_seconds = max(0, int(current_time - mute_start))
    seconds_since_last = max(0, int(current_time - last_notify))
    
    log_info(f"[{time_str}] 已静音: {format_time(total_seconds)}，距离上次通知: {format_time(seconds_since_last)}")
    
    # 异常静音通知
    if total_seconds >= T and seconds_since_last >= T:
        msg = f"🔇 静音提醒：已持续 {format_time(total_seconds)}"
        log_warning(f"[{time_str}] {msg}")
        
        # 发送异常通知（先发图片，再发合并文字）
        send_abnormal_notification(msg)
        
        last_notify = current_time
        notified = True
    
    write_state({
        "mute_start": mute_start,
        "last_notify": last_notify,
        "notified": notified
    })
    
    return True

def script_description():
    return "静音检测 (异常截图)"

def script_load(settings):
    run()

def script_unload():
    pass
