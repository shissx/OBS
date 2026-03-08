#移动截图
import os, glob, shutil, time
from datetime import datetime
import obspython as obs

# ============================================
# 可配置参数
# ============================================
DEBUG = ${Debug}
SCREENSHOT_FOLDER = ""           # 为空则自动获取OBS录制路径
MOVE_TO_SUBFOLDER = "截图"        # 移动到的子文件夹名称
PRE_DELAY = 1                    # 代码执行前延迟(秒)，保证之前任务完成

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
            import configparser
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

def manage_screenshots():
    """智能管理截图：有图则移动，无图则清理空文件夹"""
    folder = get_screenshot_folder()
    target_folder = os.path.join(folder, MOVE_TO_SUBFOLDER)
    
    log_info(f"源文件夹: {folder}")
    
    # 1. 先查找所有截图文件
    try:
        screenshot_files = glob.glob(os.path.join(folder, "Screenshot*.png"))
        has_screenshots = len(screenshot_files) > 0
        
        log_info(f"找到 {len(screenshot_files)} 个截图文件")
        
        # 2. 如果有截图
        if has_screenshots:
            # 确保目标文件夹存在
            if not os.path.exists(target_folder):
                try:
                    os.makedirs(target_folder)
                    log_info(f"创建文件夹: {target_folder}")
                except Exception as e:
                    log_info(f"创建文件夹失败: {e}")
                    return False
            
            # 移动所有截图
            moved_count = 0
            for file_path in screenshot_files:
                filename = os.path.basename(file_path)
                target_path = os.path.join(target_folder, filename)
                
                # 如果目标文件已存在，添加时间戳避免覆盖
                if os.path.exists(target_path):
                    name, ext = os.path.splitext(filename)
                    timestamp = datetime.now().strftime("%H%M%S")
                    new_filename = f"{name}_{timestamp}{ext}"
                    target_path = os.path.join(target_folder, new_filename)
                
                try:
                    shutil.move(file_path, target_path)
                    log_info(f"移动: {filename} -> {MOVE_TO_SUBFOLDER}/")
                    moved_count += 1
                except Exception as e:
                    log_info(f"移动失败 {filename}: {e}")
            
            log_info(f"移动完成，共移动 {moved_count} 个文件")
            return True
        
        # 3. 如果没有截图
        else:
            # 检查目标文件夹是否存在
            if os.path.exists(target_folder):
                try:
                    # 检查文件夹是否为空
                    if not os.listdir(target_folder):
                        os.rmdir(target_folder)
                        log_info(f"删除空文件夹: {target_folder}")
                    else:
                        log_info(f"文件夹非空，保留: {target_folder}")
                except Exception as e:
                    log_info(f"处理文件夹失败: {e}")
            else:
                log_info("无截图，且目标文件夹不存在，无需操作")
            
            return True
        
    except Exception as e:
        log_info(f"处理截图失败: {e}")
        return False

def run():
    now = datetime.now()
    time_str = now.strftime("%H:%M:%S")
    
    log_info(f"[{time_str}] ===== 截图移动脚本被触发 =====")
    
    # 前置延迟，确保之前的任务完成
    if PRE_DELAY > 0:
        log_info(f"等待 {PRE_DELAY} 秒...")
        time.sleep(PRE_DELAY)
    
    manage_screenshots()
    
    return True

def script_description():
    return "智能管理截图文件夹"

def script_load(settings):
    run()

def script_unload():
    pass
