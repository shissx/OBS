#截图消息
import os, glob, base64, hashlib, requests, json, time, configparser
from datetime import datetime
import obspython as obs

# ============================================
# 可配置参数
# ============================================
DEBUG = ${Debug}
WEBHOOK = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=${BotKey}"
SCREENSHOT_FOLDER = ""           # 为空则自动获取OBS录制路径
TEXT_IMG_DELAY = 1               # 图片和文字发送间隔(秒)

# ============================================
# 全局变量
# ============================================
cached_folder = ""

def log_info(msg):
    if DEBUG:
        obs.script_log(obs.LOG_INFO, msg)
        
def log_warning(msg):
    if DEBUG:  # 加上DEBUG控制
        obs.script_log(obs.LOG_WARNING, msg)

def get_screenshot_folder():
    """获取截图文件夹路径（带缓存）"""
    global cached_folder
    
    if SCREENSHOT_FOLDER:
        return SCREENSHOT_FOLDER
    
    if cached_folder:
        return cached_folder
    
    try:
        basic_ini = os.path.join(
            os.environ.get('APPDATA', ''),
            "obs-studio", "basic", "profiles", "未命名", "basic.ini"
        )
        
        if os.path.exists(basic_ini):
            config = configparser.ConfigParser()
            config.read(basic_ini, encoding='utf-8-sig')
            
            output_mode = config.get('Output', 'Mode', fallback='Simple')
            
            if output_mode == 'Simple':
                record_path = config.get('SimpleOutput', 'FilePath', fallback='')
            else:
                record_path = config.get('AdvOut', 'RecFilePath', fallback='')
            
            if record_path:
                cached_folder = record_path
                return cached_folder
    except:
        pass
    
    cached_folder = os.path.join(os.path.expanduser("~"), "Videos")
    return cached_folder

def send_timed_notification():
    """发送定时监控：先发图片，再发文字说明"""
    folder = get_screenshot_folder()
    
    try:
        # 1. 查找最新截图
        files = [(os.path.getmtime(f), f) for f in glob.glob(os.path.join(folder, "Screenshot*.png"))]
        if not files:
            log_info("未找到截图文件")
            return False
        
        latest_file = max(files)[1]
        filename = os.path.basename(latest_file)
        log_info(f"找到最新截图: {filename}")
        
        with open(latest_file, "rb") as f:
            img = f.read()
        
        # 2. 先发图片
        img_payload = {
            "msgtype": "image",
            "image": {
                "base64": base64.b64encode(img).decode(),
                "md5": hashlib.md5(img).hexdigest()
            }
        }
        
        img_response = requests.post(
            WEBHOOK,
            headers={"Content-Type": "application/json"},
            data=json.dumps(img_payload),
            timeout=10
        )
        
        if img_response.status_code != 200:
            log_info(f"图片发送失败: {img_response.status_code}")
            return False
        
        # 3. 等待设定的时间
        time.sleep(TEXT_IMG_DELAY)
        
        # 4. 再发文字说明
        caption = f"⏱️定时监控 {datetime.now().strftime('%H:%M')}"
        text_payload = {
            "msgtype": "text",
            "text": {"content": caption}
        }
        
        text_response = requests.post(
            WEBHOOK,
            headers={"Content-Type": "application/json"},
            data=json.dumps(text_payload),
            timeout=5
        )
        
        if text_response.status_code == 200:
            log_info("定时监控发送成功（先图后文）")
            return True
        else:
            log_info(f"文字发送失败: {text_response.status_code}")
            return False
        
    except Exception as e:
        log_info(f"定时监控异常: {e}")
        return False

def run():
    now = datetime.now()
    time_str = now.strftime("%H:%M:%S")
    
    log_info(f"[{time_str}] ===== 定时截图宏被触发 =====")
    send_timed_notification()
    
    return True

def script_description():
    return "定时截图 (先图后文)"

def script_load(settings):
    run()

def script_unload():
    pass
