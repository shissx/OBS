import time
import tkinter as tk
import requests as req
import threading
import queue
import traceback
import logging
import pythoncom
from threading import Thread
from pycaw.pycaw import AudioUtilities, IAudioMeterInformation

# 注意，请先修改key

class SmartAudioMonitor:
    def __init__(self):
        # ==================== 程序运行状态变量 ====================
        self.is_window_active = False      # 标志位：是否有弹窗正在显示（防止弹窗重叠）
        self.silence_duration = 0          # 当前音频异常的持续时间（单位：秒）
        self.last_alert_time = 0           # 上次触发提醒时的时间戳（用于控制提醒间隔）
        self.alert_count = 0               # 提醒总次数（无限提醒模式不计入此计数）
        self._running = True               # 程序运行状态标志（True=运行中，False=停止）
        self._threads = []                 # 跟踪所有创建的线程，便于后续清理
        self._speaker = None               # 语音播放器对象（单例模式，避免重复创建）
        self._root = None                  # Tkinter根窗口对象
        self._window_queue = queue.Queue() # 弹窗任务队列（用于线程间通信）
        
        # ==================== 应用检测配置 ====================
        self.allowed_apps = ["msedge", "chrome", "QQBrowser"]  # 白名单：只监控这些应用的音频
        self.strict_mode = False             # 严格模式开关：True=检测任何音频，False=只检测白名单应用
        
        # ==================== 提醒开关配置 ====================
        self.wechat_alert_enabled = True     # 是否启用企业微信提醒
        self.sound_alert_enabled = True      # 是否启用语音提醒
        self.popup_alert_enabled = True      # 是否启用弹窗提醒
        
        # ==================== 企业微信配置 ====================
        self.wechat_webhook_url = "https://qyapi.weixin.qq.com/cgi-bin/webhook/send?key=test"  # 企业微信机器人Webhook地址
        
        # ==================== 时间控制配置 ====================
        self.check_interval = 2             # 检测间隔时间（单位：秒）- 每隔多久检测一次音频状态
        self.first_alert = 60               # 首次提醒阈值（单位：秒）- 异常持续多久后触发首次提醒
        self.repeat_alert = 60              # 重复提醒间隔（单位：秒）- 首次提醒后，每隔多久再次提醒
        self.infinite_start = 120           # 无限提醒开始时间（单位：秒）- 异常持续多久后进入无限提醒模式
        self.window_duration = 3            # 弹窗显示时长（单位：秒）- 弹窗自动关闭的时间
        self.infinite_interval = 180        # 无限提醒间隔（单位：秒）- 进入无限模式后，每隔多久提醒一次
        
        # ==================== 音频检测配置 ====================
        self.audio_threshold = 0.001           # 音频音量阈值（0-1之间）- 超过此值认为有声音，低于此值认为静音
        
        # ==================== 语音提醒配置 ====================
        self.normal_alert_message = "音频异常！"           # 普通提醒时的语音内容
        self.infinite_alert_message = "音频持续异常，请立即处理！"  # 无限提醒时的语音内容
        
        # ==================== 初始化日志 ====================
        self._setup_logging()                  # 调用日志配置方法，初始化日志系统
    
    def _setup_logging(self):
        """配置简洁日志系统"""
        # 清空之前的日志配置
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        
        # 自定义日志格式
        class SimpleFormatter(logging.Formatter):
            def format(self, record):
                if record.levelno >= logging.ERROR:
                    return f"{self.formatTime(record, '%H:%M:%S')}     ❌ {record.getMessage()}"
                elif record.levelno >= logging.WARNING:
                    return f"{self.formatTime(record, '%H:%M:%S')}     ⚠ {record.getMessage()}"
                else:
                    return f"{self.formatTime(record, '%H:%M:%S')}     ℹ️ {record.getMessage()}"
        
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(SimpleFormatter())
        console_handler.setLevel(logging.INFO)
        
        file_handler = logging.FileHandler('audio_monitor.log', encoding='utf-8')
        file_formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(file_formatter)
        file_handler.setLevel(logging.DEBUG)
        
        logging.basicConfig(
            level=logging.DEBUG,
            handlers=[console_handler, file_handler]
        )
        
        logging.getLogger("urllib3").setLevel(logging.WARNING)
        logging.getLogger("requests").setLevel(logging.WARNING)
        
        self.logger = logging.getLogger(__name__)
    
    def _init_tkinter(self):
        """初始化Tkinter（在主线程中运行）"""
        try:
            self._root = tk.Tk()
            self._root.withdraw()  # 隐藏主窗口
            self._root.title("音频监控器")
            self.logger.info("Tkinter初始化成功")
            return True
        except Exception as e:
            self.logger.error(f"Tkinter初始化失败: {e}")
            return False
    
    def check_status(self, audio_apps):
        """检查音频状态是否正常"""
        if not audio_apps:
            return False, "完全静音"
                
        if not self.strict_mode:
            for app in audio_apps:
                app_lower = app.lower()
                for allowed in self.allowed_apps:
                    app_name_without_ext = app_lower.replace('.exe', '')
                    if allowed.lower() in app_name_without_ext:
                        return True, f"正常: {app}"
                
            app_list = "，".join(audio_apps)
            return False, f"非监控应用: {app_list}"
        
        return True, "有音频"
    
    def play_sound(self, is_infinite=False):
        """播放提醒声音"""
        if not self.sound_alert_enabled:
            return
            
        try:
            import win32com.client
            try:
                pythoncom.CoInitialize()
            except:
                pass
            
            if self._speaker is None:
                self._speaker = win32com.client.Dispatch("SAPI.SpVoice")
            
            if is_infinite:
                self._speaker.Speak(self.infinite_alert_message)
            else:
                self._speaker.Speak(self.normal_alert_message)
        except Exception as e:
            self.logger.error(f"语音播放失败: {e}")
        finally:
            try:
                pythoncom.CoUninitialize()
            except:
                pass
    
    def _create_window(self, alert_num, reason):
        """创建弹窗（在主线程中调用）"""
        try:
            if self.is_window_active:
                return  # 已经有弹窗，跳过
                
            self.is_window_active = True
            alert = tk.Toplevel(self._root)
            
            is_infinite = self.silence_duration > self.infinite_start
            
            if is_infinite:
                alert.title("⚠️ 持续异常")
                title, color = "🔴 持续异常警告", '#dc3545'
                info = f"{reason}\n已异常 {self.silence_duration}秒"
                close = f"{self.window_duration}秒后刷新"
            else:
                alert.title(f"音频异常 ({alert_num})")
                title, color = "🔇 音频异常", '#343a40'
                info = f"{reason}\n第{alert_num}次提醒"
                close = f"{self.window_duration}秒后关闭"
            
            alert.attributes('-topmost', True)
            alert.configure(bg='#f8f9fa')
            alert.minsize(300, 150)  # 新增：设置最小宽度和高度
            
            tk.Label(alert, text=title, font=("微软雅黑", 14, "bold"), 
                   bg='#f8f9fa', fg=color).pack(pady=10)
            tk.Label(alert, text=info, font=("微软雅黑", 11),
                   bg='#f8f9fa', fg='#6c757d').pack(pady=5)
            tk.Label(alert, text=close, font=("微软雅黑", 9),
                   bg='#f8f9fa', fg='#adb5bd').pack(pady=5)
            
            alert.update_idletasks()
            width = alert.winfo_reqwidth()
            height = alert.winfo_reqheight()
            x = (alert.winfo_screenwidth() // 2) - (width // 2)
            y = (alert.winfo_screenheight() // 2) - (height // 2)
            alert.geometry(f'{width}x{height}+{x}+{y}')
            
            # 设置自动关闭
            def close_window():
                try:
                    alert.destroy()
                except:
                    pass
                finally:
                    self.is_window_active = False
            
            # 绑定手动关闭事件
            def on_closing():
                self.is_window_active = False
                alert.destroy()
            
            alert.protocol("WM_DELETE_WINDOW", on_closing)
            
            # 设置自动关闭定时器
            alert.after(self.window_duration * 1000, close_window)
            
        except Exception as e:
            self.logger.error(f"弹窗创建失败: {e}")
            self.is_window_active = False
    
    def _process_window_queue(self):
        """处理弹窗队列"""
        try:
            while not self._window_queue.empty():
                alert_num, reason = self._window_queue.get_nowait()
                self._create_window(alert_num, reason)
        except:
            pass
    
    def show_window(self, alert_num, reason):
        """添加弹窗任务到队列"""
        if not self.popup_alert_enabled:
            return
            
        self._window_queue.put((alert_num, reason))
    
    def send_wechat_alert(self, content):
        """发送企业微信提醒"""
        if not self.wechat_alert_enabled:
            return
            
        def _send():
            try:
                response = req.post(
                    self.wechat_webhook_url,
                    json={"msgtype": "text", "text": {"content": content}},
                    timeout=5
                )
                if response.status_code == 200:
                    self.logger.info("企业微信: 提醒发送成功")
                else:
                    self.logger.warning(f"企业微信: 提醒发送失败: {response.status_code}")
            except req.exceptions.Timeout:
                self.logger.warning("企业微信: 提醒发送超时")
            except Exception as e:
                self.logger.error(f"企业微信: 提醒发送异常: {e}")
        
        wechat_thread = Thread(target=_send, daemon=True)
        wechat_thread.start()
        self._threads.append(wechat_thread)

    def alert(self, alert_num, reason=""):
        """触发提醒（带异常处理）"""
        try:
            # 判断是否是无限提醒（alert_num为负数表示无限提醒）
            is_infinite = alert_num < 0 or self.silence_duration > self.infinite_start
            
            # 计算无限提醒次数（如果有的话）
            if is_infinite:
                infinite_reminder_count = int((self.silence_duration - self.infinite_start) / self.infinite_interval) + 1
                if infinite_reminder_count < 1:
                    infinite_reminder_count = 1
            else:
                infinite_reminder_count = 0
            
            # 播放声音（在新线程中，异常不会影响主线程）
            if self.sound_alert_enabled:
                try:
                    sound_thread = Thread(target=self.play_sound, args=(is_infinite,), daemon=True)
                    sound_thread.start()
                    self._threads.append(sound_thread)
                except Exception as e:
                    self.logger.error(f"声音提醒线程启动失败: {e}")
            
            # 准备提醒内容
            try:
                if is_infinite:
                    clean_reason = reason.replace('[持续]', '')
                    # 修复：使用正确的格式
                    content = f"🔴 持续异常 {self.silence_duration}秒（{infinite_reminder_count}）: {clean_reason}"
                    wechat_content = content
                else:
                    actual_num = max(1, alert_num) if alert_num > 0 else 1
                    content = f"🔇 音频异常（{actual_num}）: {reason}"
                    wechat_content = content
            except Exception as e:
                self.logger.error(f"提醒内容生成失败: {e}")
                # 使用默认内容
                if is_infinite:
                    wechat_content = f"🔴 持续异常 {self.silence_duration}秒"
                else:
                    wechat_content = f"🔇 音频异常提醒"
            
            # 发送企业微信提醒
            try:
                self.send_wechat_alert(wechat_content)
            except Exception as e:
                self.logger.error(f"企业微信发送失败: {e}")
            
            # 显示弹窗
            if self.popup_alert_enabled:
                try:
                    reason_display = reason.replace(":", "\n").replace("，", "\n")
                    self.show_window(alert_num, reason_display)
                except Exception as e:
                    self.logger.error(f"弹窗显示失败: {e}")
            
            self.last_alert_time = time.time()
            
            # 更新计数
            try:
                if not is_infinite:
                    self.alert_count += 1
                    self.logger.info(f"触发提醒: {reason}（{self.alert_count}）")
                else:
                    # 无限提醒不增加总计数
                    self.logger.info(f"无限提醒: {reason}（第{infinite_reminder_count}次）")
            except Exception as e:
                self.logger.error(f"计数更新失败: {e}")
                
        except Exception as e:
            # 捕获alert方法中的所有未处理异常
            self.logger.error(f"提醒处理失败: {e}")
            self.logger.error(traceback.format_exc())
            # 注意：这里不重新抛出异常，避免递归
    
    def _cleanup_threads(self):
        """清理已完成的线程"""
        self._threads = [t for t in self._threads if t.is_alive()]

    def _clean_process_name(self, process_name):
        """清理和验证进程名"""
        if not process_name:
            return None
        
        # 确保是字符串
        try:
            name = str(process_name).strip()
        except:
            return None
        
        # 过滤无效名称
        if not name or len(name) == 0:
            return None
        
        # 过滤常见系统进程
        invalid_names = [
            '', 'system', 'system idle process', 'idle', 
            'svchost', 'dwm', 'csrss', 'lsass', 'smss', 
            'wininit', 'winlogon', 'services', 'taskhostw',
            'runtimebroker', 'ctfmon', 'conhost', 'sihost',
            'searchindexer', 'searchui', 'dllhost', 'backgroundtaskhost'
        ]
        
        name_lower = name.lower()
        for invalid in invalid_names:
            if name_lower == invalid or name_lower.startswith(invalid + '#'):
                return None
        
        # 去掉.exe扩展名
        if name_lower.endswith('.exe'):
            name = name[:-4]
        
        # 长度限制
        if len(name) > 260 or len(name) < 1:
            return None
        
        return name
    
    def get_audio_apps(self):
        """获取正在播放音频的应用列表（完整保护版）"""
        import threading
        import queue
        
        result_queue = queue.Queue()
        start_time = time.time()
        
        def _execute_detection():
            try:
                pythoncom.CoInitialize()
                
                temp_apps = []
                seen_apps = set()
                
                try:
                    sessions = AudioUtilities.GetAllSessions()
                except Exception as e:
                    self.logger.error(f"获取音频会话失败: {e}")
                    result_queue.put([])
                    return
                
                for session in sessions:
                    try:
                        # 检查会话和进程对象
                        if not session or not session.Process:
                            continue
                        
                        # 安全获取进程名
                        try:
                            process_name = session.Process.name()
                        except Exception:
                            continue
                        
                        # 验证进程名
                        if not process_name or not isinstance(process_name, str):
                            continue
                        
                        # 清理进程名
                        app_name = self._clean_process_name(process_name)
                        if not app_name:
                            continue
                        
                        # 检查音频状态
                        try:
                            meter = session._ctl.QueryInterface(IAudioMeterInformation)
                            peak_value = meter.GetPeakValue()
                        except Exception:
                            continue
                        
                        # 检查是否超过阈值
                        if peak_value > self.audio_threshold:
                            if app_name not in seen_apps:
                                temp_apps.append(app_name)
                                seen_apps.add(app_name)
                                
                    except Exception as e:
                        self.logger.debug(f"单个会话处理失败: {e}")
                        continue
                
                result_queue.put(temp_apps)
                
            except Exception as e:
                self.logger.error(f"音频检测内部错误: {e}")
                result_queue.put([])
            finally:
                try:
                    pythoncom.CoUninitialize()
                except:
                    pass
        
        # 在新线程中执行检测
        thread = threading.Thread(target=_execute_detection, daemon=True)
        thread.start()
        
        # 设置超时（5秒）
        thread.join(timeout=5.0)
        
        if thread.is_alive():
            elapsed = time.time() - start_time
            self.logger.warning(f"音频检测超时（{elapsed:.1f}秒）")
            return []
        
        try:
            apps = result_queue.get_nowait()
            elapsed = time.time() - start_time
            
            # 记录性能（如果超过阈值）
            if elapsed > 2.0:
                self.logger.info(f"音频检测完成，耗时{elapsed:.2f}秒，找到{len(apps)}个应用")
            
            return apps
        except queue.Empty:
            self.logger.warning("音频检测结果队列为空")
            return []
    
    def cleanup(self):
        """清理资源"""
        self.logger.info("开始清理资源...")
        self._running = False
        
        for thread in self._threads:
            if thread.is_alive():
                thread.join(timeout=1.0)
        
        if self._root:
            try:
                self._root.quit()
                self._root.destroy()
            except:
                pass
        
        self.logger.info("资源清理完成")
    
    def run_monitor_loop(self):
        """运行监控循环（在单独线程中）"""
        abnormal = 0
        last_infinite = 0
        last_print_time = 0
        last_success_time = time.time()
        consecutive_errors = 0
        
        try:
            while self._running:
                try:
                    loop_start = time.time()
                    current_time = time.strftime("%H:%M:%S")
                    
                    # 处理弹窗队列（如果主线程在处理Tkinter事件，这里不需要）
                    
                    # 获取音频应用列表
                    apps = self.get_audio_apps()
                    
                    normal, reason = self.check_status(apps)
                    
                    if normal:
                        if abnormal > 0:
                            print()
                            app_list = "，".join(apps) if apps else "无应用"
                            print(f"{current_time} ✅ 恢复正常 - {app_list}")
                        elif apps:
                            app_list = "，".join(apps)
                            print(f"{current_time} 🔊 正常 - {app_list}")
                        
                        abnormal = 0
                        self.silence_duration = 0
                            
                    else:
                        abnormal += 1
                        self.silence_duration = abnormal * self.check_interval
                        
                        first_count = int(self.first_alert / self.check_interval)
                        
                        if abnormal < first_count:
                            progress = f"({self.silence_duration}/{self.first_alert}秒)"
                            if loop_start - last_print_time >= 1:
                                print(f"\r\033[K{current_time} ⚠️  检测中 {progress} - {reason}", end='', flush=True)
                                last_print_time = loop_start
                        else:
                            if loop_start - last_print_time >= 1:
                                print(f"\r\033[K{current_time} ⚠️  异常 {self.silence_duration}秒 - {reason}", end='', flush=True)
                                last_print_time = loop_start
                            
                            now = time.time()
                            
                            # 1. 无限提醒
                            if (self.silence_duration >= self.infinite_start and 
                                not self.is_window_active and
                                (last_infinite == 0 or now - last_infinite >= self.infinite_interval)):
                                
                                print()
                                infinite_count = int((self.silence_duration - self.infinite_start) / self.infinite_interval) + 1
                                print(f"{current_time}     🔴 第{infinite_count}次无限提醒 [{self.silence_duration}秒]")
                                
                                try:
                                    # 修复：传入正确的参数，并避免递归调用
                                    # 注意：这里传入的是 infinite_count，不是 0，但 alert_num 应该是负数表示无限提醒
                                    self.alert(-infinite_count, f"[持续]{reason}")
                                except Exception as e:
                                    self.logger.error(f"无限提醒失败: {e}")
                                    print(f"{current_time}     ❌ 提醒发送失败")
                                
                                last_infinite = now

                            # 2. 首次提醒
                            elif abnormal == first_count and not self.is_window_active:
                                print()
                                print(f"{current_time}     🚨 首次提醒")
                                
                                try:
                                    self.alert(1, reason)
                                except Exception as e:
                                    self.logger.error(f"首次提醒失败: {e}")
                                    print(f"{current_time}     ❌ 提醒发送失败")

                            # 3. 重复提醒
                            elif (abnormal > first_count and 
                                  not self.is_window_active and
                                  now - self.last_alert_time >= self.repeat_alert):
                                print()
                                if self.silence_duration < self.infinite_start:
                                    print(f"{current_time}     🚨 第{self.alert_count+1}次提醒")
                                else:
                                    infinite_count = int((self.silence_duration - self.infinite_start) / self.infinite_interval) + 1
                                    print(f"{current_time}     🔴 无限提醒状态 [{self.silence_duration}秒]")
                                
                                try:
                                    self.alert(self.alert_count + 1, reason)
                                except Exception as e:
                                    self.logger.error(f"重复提醒失败: {e}")
                                    print(f"{current_time}     ❌ 提醒发送失败")
                    
                    last_success_time = time.time()
                    consecutive_errors = 0
                    
                    loop_duration = time.time() - loop_start
                    
                    if loop_duration > self.check_interval:
                        print(f"\n{current_time} ⚠️  警告：循环耗时 {loop_duration:.1f}秒")
                    
                    sleep_time = max(0.01, self.check_interval - loop_duration)
                    if sleep_time > 0:
                        time.sleep(sleep_time)
                        
                except KeyboardInterrupt:
                    raise
                except Exception as e:
                    consecutive_errors += 1
                    error_time = time.strftime("%H:%M:%S")
                    error_msg = f"循环异常 ({consecutive_errors}/10): {str(e)[:100]}"
                    
                    self.logger.error(f"{error_msg}")
                    print(f"\n{error_time} ❌ {error_msg}")
                    
                    if consecutive_errors > 10:
                        print(f"\n{error_time} ⚠️  连续错误过多，等待60秒")
                        time.sleep(60)
                        consecutive_errors = 0
                    else:
                        time.sleep(self.check_interval)
                    
        except KeyboardInterrupt:
            pass
        except Exception as e:
            self.logger.error(f"监控循环异常终止: {e}")
        finally:
            self.cleanup()
    
    def run(self):
        """运行主程序"""        
        print("🎧 智能静音检测器")
        print("=" * 60)
        print(f"检测模式: {'完全静音模式' if self.strict_mode else '兼容模式'}")
        print(f"监控应用: {', '.join(self.allowed_apps)}")
        print("-" * 60)
        print(f"检测间隔: {self.check_interval}秒")
        print(f"首次提醒: 异常{self.first_alert}秒后")
        print(f"重复提醒: 每{self.repeat_alert}秒一次")
        print(f"无限提醒: 异常{self.infinite_start}秒后开始，每{self.infinite_interval}秒一次")
        print(f"弹窗时长: {self.window_duration}秒")
        print(f"音频阈值: {self.audio_threshold}")
        print("-" * 60)
        print(f"提醒开关:")
        print(f"  企业微信: {'✅ 启用' if self.wechat_alert_enabled else '❌ 禁用'}")
        print(f"  声音提醒: {'✅ 启用' if self.sound_alert_enabled else '❌ 禁用'}")
        print(f"  弹窗提醒: {'✅ 启用' if self.popup_alert_enabled else '❌ 禁用'}")
        print("-" * 60)
        print("按 Ctrl+C 退出程序")
        print("=" * 60 + "\n")
        
        self.logger.info("🎧 智能静音检测器启动")
        
        # 启动Tkinter主线程
        import threading
        tkinter_ready = threading.Event()
        
        def tkinter_main():
            """Tkinter主事件循环"""
            try:
                if self._init_tkinter():
                    tkinter_ready.set()
                    
                    # 定期处理弹窗队列
                    def process_queue():
                        if not self._running:
                            return
                        try:
                            self._process_window_queue()
                            self._root.after(100, process_queue)  # 每100ms检查一次
                        except:
                            pass
                    
                    # 启动队列处理
                    self._root.after(100, process_queue)
                    
                    # 运行Tkinter主循环
                    self._root.mainloop()
                else:
                    tkinter_ready.set()
            except Exception as e:
                self.logger.error(f"Tkinter主循环异常: {e}")
                tkinter_ready.set()
        
        # 启动Tkinter线程
        tkinter_thread = Thread(target=tkinter_main, daemon=True)
        tkinter_thread.start()
        
        # 等待Tkinter初始化完成
        tkinter_ready.wait(timeout=5)
        
        if not self._root:
            self.logger.warning("Tkinter初始化失败，弹窗功能将不可用")
            self.popup_alert_enabled = False
        
        # 启动监控循环（在主线程中运行）
        try:
            self.run_monitor_loop()
        except KeyboardInterrupt:
            print(f"\n\n程序结束")
            print(f"共提醒 {self.alert_count} 次")
            self.logger.info(f"程序正常结束，共提醒 {self.alert_count} 次")
        finally:
            self._running = False
            if self._root:
                try:
                    self._root.quit()
                except:
                    pass

# ====== 使用示例 ======
if __name__ == "__main__":
    monitor = SmartAudioMonitor()
    
    # ====== 可选：修改配置 ======
    # monitor.allowed_apps = ["obs", "potplayer", "vlc"]
    # monitor.strict_mode = False
    # monitor.check_interval = 1
    # monitor.first_alert = 5
    # monitor.repeat_alert = 8
    # monitor.infinite_start = 20
    # monitor.infinite_interval = 5
    # monitor.window_duration = 4
    # monitor.audio_threshold = 0.0005
    # monitor.normal_alert_message = "发现OBS异常，请检查音频！"
    # monitor.infinite_alert_message = "音频长时间异常！"
    
    # ====== 提醒开关配置 ======
    # monitor.wechat_alert_enabled = False
    # monitor.sound_alert_enabled = False
    # monitor.popup_alert_enabled = False
    
    # ====== 自定义企业微信Webhook ======
    # monitor.wechat_webhook_url = "你的企业微信Webhook地址"
    
    try:
        monitor.run()
    except Exception as e:
        print(f"程序异常终止: {e}")
        logging.error(f"程序异常终止: {e}")
        logging.error(traceback.format_exc())
