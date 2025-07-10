import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import vlc
import json
import os
import logging
import time
from datetime import datetime
import threading

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

VIDEO_DIR = r"F:/Study/research/desire-qa/videos/"
JSON_FILE = r"F:/Study/research/desire-qa/desire-qa/desire_oriented_vqa.json"


def load_annotations_from_json(video_id):
    """从JSON文件加载标注数据"""
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # 1. 首先直接匹配key
        if video_id in data:
            logging.info(f"直接匹配到视频ID: {video_id}")
            return data[video_id]

        # 2. 通过metadata中的video_id匹配
        for key, value in data.items():
            if "metadata" in value and "video_id" in value["metadata"]:
                metadata_video_id = value["metadata"]["video_id"]
                if metadata_video_id == video_id:
                    logging.info(f"通过metadata匹配到视频ID: {video_id}")
                    return value

        # 3. 通过metadata中的youtube_id + 时间匹配
        for key, value in data.items():
            if "metadata" in value:
                metadata = value["metadata"]
                if all(k in metadata for k in ["youtube_id", "start_seconds", "end_seconds"]):
                    youtube_id = metadata["youtube_id"]
                    start_sec = metadata["start_seconds"]
                    end_sec = metadata["end_seconds"]
                    full_id = f"{youtube_id}_{start_sec}_{end_sec}"

                    if full_id == video_id:
                        logging.info(f"通过metadata构造ID匹配到视频: {video_id}")
                        return value

                    # 也匹配只有youtube_id的情况
                    if youtube_id == video_id:
                        logging.info(f"通过youtube_id匹配到视频: {video_id}")
                        return value

        # 4. 兼容旧格式
        for key, value in data.items():
            if "desire_analysis" in value:
                desire_analysis = value["desire_analysis"]
                if all(k in desire_analysis for k in ["YouTube_ID", "Start_Seconds", "End_Seconds"]):
                    youtube_id = desire_analysis["YouTube_ID"]
                    start_sec = desire_analysis["Start_Seconds"]
                    end_sec = desire_analysis["End_Seconds"]
                    full_id = f"{youtube_id}_{start_sec}_{end_sec}"

                    if full_id == video_id or youtube_id == video_id:
                        logging.info(f"通过旧格式匹配到视频: {video_id}")
                        return value

        # 5. 模糊匹配：如果输入的video_id包含下划线，尝试匹配基本ID
        if '_' in video_id:
            base_video_id = video_id.split('_')[0]
            for key, value in data.items():
                if key == base_video_id:
                    logging.info(f"通过基本ID匹配到视频: {base_video_id}")
                    return value

                # 检查metadata中的youtube_id
                if "metadata" in value and "youtube_id" in value["metadata"]:
                    if value["metadata"]["youtube_id"] == base_video_id:
                        logging.info(f"通过metadata基本ID匹配到视频: {base_video_id}")
                        return value

        logging.warning(f"未在JSON中找到视频ID: {video_id}")
        return {}

    except Exception as e:
        logging.error(f"加载JSON文件时出错: {str(e)}")
        return {}


def get_annotated_video_ids():
    """获取所有已标注的视频ID"""
    ids = []
    try:
        with open(JSON_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)

        for key, value in data.items():
            # 1. 添加JSON中的key作为ID
            ids.append(key)

            # 2. 如果有metadata，也添加相关ID
            if "metadata" in value:
                metadata = value["metadata"]

                # 添加metadata中的video_id
                if "video_id" in metadata:
                    ids.append(metadata["video_id"])

                # 添加通过metadata构造的完整ID
                if all(k in metadata for k in ["youtube_id", "start_seconds", "end_seconds"]):
                    youtube_id = metadata["youtube_id"]
                    start_sec = metadata["start_seconds"]
                    end_sec = metadata["end_seconds"]
                    full_id = f"{youtube_id}_{start_sec}_{end_sec}"
                    ids.append(full_id)

                    # 也添加youtube_id
                    ids.append(youtube_id)

            # 3. 兼容旧格式
            if "desire_analysis" in value:
                desire_analysis = value["desire_analysis"]
                if all(k in desire_analysis for k in ["YouTube_ID", "Start_Seconds", "End_Seconds"]):
                    youtube_id = desire_analysis["YouTube_ID"]
                    start_sec = desire_analysis["Start_Seconds"]
                    end_sec = desire_analysis["End_Seconds"]
                    full_id = f"{youtube_id}_{start_sec}_{end_sec}"
                    ids.append(full_id)
                    ids.append(youtube_id)

    except Exception as e:
        logging.error(f"解析JSON时出错: {str(e)}")

    # 去重并返回
    return list(set(ids))


class VideoApp:
    def __init__(self, root):
        self.root = root
        self.root.title("视频标注可视化 - 增强版")
        self.root.geometry("1200x800")

        # 创建主框架
        self.setup_ui()

        # 初始化变量
        self.is_playing = False
        self.annotations = {}
        self.current_frame = 0
        self.frame_count = 0
        self.video_files = self.get_video_files()
        self.current_video_index = 0
        self.auto_mode = False
        self.current_video_id = None
        self.seeking = False

        # 创建VLC实例和播放器，添加字幕样式配置
        self.vlc_instance = vlc.Instance([
            '--intf', 'dummy',
            '--no-xlib',
            '--no-video-title-show',
            '--quiet',
            '--sub-text-scale=150',  # 字幕大小（150%）
            '--freetype-color=16777215',  # 字 rot 色（白色）
            '--freetype-outline-color=0',  # 字幕描边颜色（黑色）
            '--freetype-font=SimHei'  # 使用支持中文的字体
        ])
        self.media_player = self.vlc_instance.media_player_new()

        # 开始更新进度条
        self.update_progress()

    def setup_ui(self):
        """设置用户界面"""
        main_container = tk.Frame(self.root)
        main_container.pack(fill="both", expand=True, padx=10, pady=10)

        left_frame = tk.Frame(main_container)
        left_frame.pack(side="left", fill="both", expand=True)

        self.video_frame = tk.Frame(left_frame, bg="black")
        self.video_frame.pack(fill="both", expand=True)

        self.canvas = tk.Canvas(self.video_frame, width=640, height=360, bg="black")
        self.canvas.pack(fill="both", expand=True)

        control_frame = tk.Frame(left_frame)
        control_frame.pack(fill="x", pady=5)

        mode_frame = tk.Frame(control_frame)
        mode_frame.pack(fill="x", pady=5)

        tk.Label(mode_frame, text="播放模式:").pack(side="left")
        self.auto_mode_button = tk.Button(mode_frame, text="自动播放模式", command=self.set_auto_mode)
        self.auto_mode_button.pack(side="left", padx=5)
        self.id_mode_button = tk.Button(mode_frame, text="指定ID播放模式", command=self.set_id_mode)
        self.id_mode_button.pack(side="left", padx=5)

        id_frame = tk.Frame(control_frame)
        id_frame.pack(fill="x", pady=5)

        self.id_label = tk.Label(id_frame, text="视频ID:")
        self.id_label.pack(side="left")
        self.id_entry = tk.Entry(id_frame, width=30)
        self.id_entry.pack(side="left", padx=5)

        button_frame = tk.Frame(control_frame)
        button_frame.pack(fill="x", pady=5)

        self.load_button = tk.Button(button_frame, text="加载视频", command=self.load_video)
        self.load_button.pack(side="left", padx=5)
        self.load_prev_button = tk.Button(button_frame, text="上一个视频", command=self.load_previous_video)
        self.load_prev_button.pack(side="left", padx=5)
        self.load_prev_button.config(state="disabled")

        self.progress = ttk.Scale(control_frame, from_=0, to=100, orient="horizontal",
                                  command=self.on_progress_change)
        self.progress.pack(fill="x", pady=5)

        self.progress.bind('<Button-1>', self.on_progress_click)
        self.progress.bind('<ButtonRelease-1>', self.on_progress_release)

        play_frame = tk.Frame(control_frame)
        play_frame.pack(fill="x", pady=5)

        self.play_button = tk.Button(play_frame, text="播放", command=self.play)
        self.play_button.pack(side="left", padx=5)
        self.pause_button = tk.Button(play_frame, text="暂停", command=self.pause)
        self.pause_button.pack(side="left", padx=5)
        self.stop_button = tk.Button(play_frame, text="停止", command=self.stop)
        self.stop_button.pack(side="left", padx=5)

        speed_frame = tk.Frame(play_frame)
        speed_frame.pack(side="left", padx=20)

        tk.Label(speed_frame, text="播放速度:").pack(side="left")
        self.speed_var = tk.DoubleVar(value=1.0)
        self.speed_scale = ttk.Scale(speed_frame, from_=0.25, to=2.0, orient="horizontal",
                                     variable=self.speed_var, command=self.change_speed)
        self.speed_scale.pack(side="left", padx=5)
        self.speed_label = tk.Label(speed_frame, text="1.0x")
        self.speed_label.pack(side="left", padx=5)

        self.time_label = tk.Label(play_frame, text="00:00 / 00:00")
        self.time_label.pack(side="left", padx=20)

        right_frame = tk.Frame(main_container, width=500)
        right_frame.pack(side="right", fill="both", padx=(10, 0))
        right_frame.pack_propagate(False)

        tk.Label(right_frame, text="标注信息", font=("Arial", 14, "bold")).pack(pady=5)

        self.notebook = ttk.Notebook(right_frame)
        self.notebook.pack(fill="both", expand=True)

        self.create_tabs()

    def create_tabs(self):
        """创建标签页"""
        self.info_frame = tk.Frame(self.notebook)
        self.notebook.add(self.info_frame, text="基本信息")

        self.info_text = scrolledtext.ScrolledText(self.info_frame, wrap=tk.WORD, height=10)
        self.info_text.pack(fill="both", expand=True, padx=5, pady=5)

        self.desire_frame = tk.Frame(self.notebook)
        self.notebook.add(self.desire_frame, text="需求分析")

        self.desire_text = scrolledtext.ScrolledText(self.desire_frame, wrap=tk.WORD, height=10)
        self.desire_text.pack(fill="both", expand=True, padx=5, pady=5)

        self.questions_frame = tk.Frame(self.notebook)
        self.notebook.add(self.questions_frame, text="问题与选项")

        self.questions_text = scrolledtext.ScrolledText(self.questions_frame, wrap=tk.WORD, height=10)
        self.questions_text.pack(fill="both", expand=True, padx=5, pady=5)

        self.timeline_frame = tk.Frame(self.notebook)
        self.notebook.add(self.timeline_frame, text="时间轴")

        self.timeline_text = scrolledtext.ScrolledText(self.timeline_frame, wrap=tk.WORD, height=10)
        self.timeline_text.pack(fill="both", expand=True, padx=5, pady=5)

    def set_auto_mode(self):
        """设置自动播放模式"""
        self.auto_mode = True
        self.load_button.config(state='normal')
        self.load_prev_button.config(state='normal')
        self.id_entry.config(state='disabled')
        self.id_label.config(state='disabled')
        self.load_button.config(text="加载下一个视频")
        logging.info("已切换到自动播放模式")

    def set_id_mode(self):
        """设置指定ID播放模式"""
        self.auto_mode = False
        self.load_button.config(state='normal')
        self.load_prev_button.config(state='disabled')
        self.id_entry.config(state='normal')
        self.id_label.config(state='normal')
        self.load_button.config(text="加载视频")
        logging.info("已切换到指定ID播放模式")

    def get_video_files(self):
        """获取视频文件列表"""
        annotated_ids = set(get_annotated_video_ids())
        files = []

        for f in os.listdir(VIDEO_DIR):
            if f.endswith(".mp4"):
                video_id = f.replace(".mp4", "")

                if video_id in annotated_ids:
                    files.append(f)
                    continue

                if '_' in video_id:
                    base_id = video_id.split('_')[0]
                    if base_id in annotated_ids:
                        files.append(f)
                        continue

                for annotated_id in annotated_ids:
                    if annotated_id.startswith(video_id) or video_id.startswith(annotated_id):
                        files.append(f)
                        break

        logging.info(f"找到 {len(files)} 个标注视频文件")
        return sorted(files)

    def load_video(self):
        """加载视频"""
        if self.auto_mode:
            if self.current_video_index >= len(self.video_files):
                messagebox.showinfo("结束", "所有标注视频已播放完毕")
                return

            video_id = self.video_files[self.current_video_index].replace(".mp4", "")
            logging.info(f"自动加载视频 {video_id}")
            self.current_video_index += 1
        else:
            video_id = self.id_entry.get().strip()
            if not video_id:
                messagebox.showerror("错误", "请输入视频ID！")
                return
            logging.info(f"加载指定视频 {video_id}")

        self.play_video_by_id(video_id)

    def load_previous_video(self):
        """加载上一个视频"""
        if not self.auto_mode:
            return

        if self.current_video_index <= 1:
            messagebox.showinfo("提示", "已是第一个视频")
            return

        self.current_video_index -= 2
        self.load_video()

    def play_video_by_id(self, video_id):
        """根据ID播放视频"""
        video_path = os.path.join(VIDEO_DIR, f"{video_id}.mp4")
        if not os.path.exists(video_path):
            messagebox.showerror("错误", f"视频文件不存在：{video_path}")
            logging.error(f"视频文件不存在：{video_path}")
            return

        subtitle_path = os.path.join(VIDEO_DIR, f"{video_id}.srt")
        if not os.path.exists(subtitle_path):
            logging.warning(f"字幕文件不存在：{subtitle_path}")
            subtitle_path = None

        try:
            self.media_player.stop()

            media = self.vlc_instance.media_new(video_path)
            if subtitle_path:
                media.add_option(f"sub-file={subtitle_path}")
            self.media_player.set_media(media)

            if os.name == 'nt':
                self.media_player.set_hwnd(self.canvas.winfo_id())
            else:
                self.media_player.set_xwindow(self.canvas.winfo_id())

            self.current_video_id = video_id

            self.media_player.play()

            self.root.after(500, self.on_video_loaded)

        except Exception as e:
            messagebox.showerror("错误", f"加载视频时发生错误：{str(e)}")
            logging.error(f"加载视频时发生错误：{str(e)}")

    def on_video_loaded(self):
        """视频加载完成后的回调"""
        try:
            if self.media_player.get_length() > 0:
                duration = self.media_player.get_length() / 1000.0
                self.progress.config(to=duration)

                self.load_annotations(self.current_video_id)

                self.is_playing = True

                logging.info(f"视频 {self.current_video_id} 加载成功，时长: {duration:.2f}秒")

                self.play()

            else:
                self.root.after(200, self.on_video_loaded)

        except Exception as e:
            logging.error(f"视频加载回调时发生错误：{str(e)}")

    def load_annotations(self, video_id):
        """加载标注信息"""
        self.annotations = load_annotations_from_json(video_id)
        self.display_annotations()

    def display_annotations(self):
        """显示标注信息"""
        for text_widget in [self.info_text, self.desire_text, self.questions_text, self.timeline_text]:
            text_widget.delete(1.0, tk.END)

        if not self.annotations:
            for text_widget in [self.info_text, self.desire_text, self.questions_text, self.timeline_text]:
                text_widget.insert(tk.END, "未找到对应标注信息")
            return

        self.display_basic_info()
        self.display_desire_analysis()
        self.display_questions()
        self.display_timeline()

    def display_basic_info(self):
        """显示基本信息"""
        info_text = f"视频文件: {self.current_video_id}\n"

        if '_' in self.current_video_id:
            parts = self.current_video_id.split('_')
            if len(parts) >= 3:
                base_id = parts[0]
                start_time = parts[1]
                end_time = parts[2]
                info_text += f"基本ID: {base_id}\n"
                info_text += f"时间段: {start_time}s - {end_time}s\n"

        info_text += "\n"

        if "metadata" in self.annotations:
            metadata = self.annotations["metadata"]
            info_text += "元数据信息:\n"
            info_text += f"  YouTube ID: {metadata.get('youtube_id', 'N/A')}\n"
            info_text += f"  开始时间: {metadata.get('start_seconds', 'N/A')}秒\n"
            info_text += f"  结束时间: {metadata.get('end_seconds', 'N/A')}秒\n"
            info_text += f"  标注时间: {metadata.get('annotated_at', 'N/A')}\n\n"

        if "desire_analysis" in self.annotations:
            desire_analysis = self.annotations["desire_analysis"]
            info_text += "旧格式元数据:\n"
            info_text += f"  YouTube ID: {desire_analysis.get('YouTube_ID', 'N/A')}\n"
            info_text += f"  开始时间: {desire_analysis.get('Start_Seconds', 'N/A')}秒\n"
            info_text += f"  结束时间: {desire_analysis.get('End_Seconds', 'N/A')}秒\n\n"

        self.info_text.insert(tk.END, info_text)

    def display_desire_analysis(self):
        """显示需求分析"""
        if "Desire" not in self.annotations:
            self.desire_text.insert(tk.END, "未找到需求分析信息")
            return

        desire = self.annotations["Desire"]
        desire_text = f"参考对象: {desire.get('Referent', 'N/A')}\n\n"

        if "Labels" in desire:
            desire_text += "需求标签:\n"
            for i, label in enumerate(desire["Labels"], 1):
                desire_text += f"\n[标签 {i}]\n"
                desire_text += f"  维度: {label.get('dimension', 'N/A')}\n"
                desire_text += f"  子标签: {label.get('sub_label', 'N/A')}\n"
                desire_text += f"  优先级: {label.get('priority', 'N/A')}\n"
                desire_text += f"  置信度: {label.get('confidence', 'N/A')}\n"
                desire_text += f"  描述: {label.get('description', 'N/A')}\n"

                if "supporting_evidence" in label:
                    desire_text += f"  支持证据: {', '.join(label['supporting_evidence'])}\n"

        self.desire_text.insert(tk.END, desire_text)

    def display_questions(self):
        """显示问题与选项"""
        if "Questions" not in self.annotations:
            self.questions_text.insert(tk.END, "未找到问题信息")
            return

        questions = self.annotations["Questions"]
        questions_text = f"共有 {len(questions)} 个问题:\n\n"

        for i, q in enumerate(questions, 1):
            questions_text += f"[问题 {i}]\n"
            questions_text += f"  问题ID: {q.get('qid', 'N/A')}\n"
            questions_text += f"  问题类型: {q.get('question_type', 'N/A')}\n"
            questions_text += f"  问题: {q.get('question', 'N/A')}\n"
            questions_text += f"  正确答案: {q.get('answer', 'N/A')}\n"
            questions_text += f"  正确答案索引: {q.get('answer_index', 'N/A')}\n"

            if "options" in q:
                questions_text += "  选项:\n"
                for j, option in enumerate(q["options"]):
                    mark = "✓" if j == q.get('answer_index', -1) else " "
                    questions_text += f"    {mark} {j}. {option}\n"

            questions_text += "\n"

        self.questions_text.insert(tk.END, questions_text)

    def display_timeline(self):
        """显示时间轴信息"""
        timeline_text = f"当前视频: {self.current_video_id}\n\n"

        if "metadata" in self.annotations:
            metadata = self.annotations["metadata"]
            start_sec = metadata.get('start_seconds', 0)
            end_sec = metadata.get('end_seconds', 0)

            timeline_text += f"视频片段: {start_sec}s - {end_sec}s\n"
            timeline_text += f"片段长度: {end_sec - start_sec}s\n\n"

        if "Questions" in self.annotations:
            timeline_text += "关键时间点:\n"
            for i, q in enumerate(self.annotations["Questions"], 1):
                timeline_text += f"  问题 {i}: {q.get('question_type', 'N/A')} 类型问题\n"

        self.timeline_text.insert(tk.END, timeline_text)

    def on_progress_click(self, event):
        """进度条被点击时"""
        self.seeking = True

    def on_progress_release(self, event):
        """进度条被释放时"""
        self.seeking = False

    def on_progress_change(self, value):
        """进度条值改变时"""
        if self.seeking and self.media_player is not None:
            try:
                time_ms = int(float(value) * 1000)
                self.media_player.set_time(time_ms)
            except Exception as e:
                logging.error(f"拖动进度条时发生错误：{str(e)}")

    def change_speed(self, value):
        """改变播放速度"""
        try:
            speed = float(value)
            if self.media_player is not None:
                self.media_player.set_rate(speed)
            self.speed_label.config(text=f"{speed:.2f}x")
        except Exception as e:
            logging.error(f"改变播放速度时发生错误：{str(e)}")

    def update_progress(self):
        """更新进度条"""
        if self.media_player is not None:
            try:
                state = self.media_player.get_state()

                if state == vlc.State.Playing:
                    self.is_playing = True
                elif state == vlc.State.Paused:
                    self.is_playing = False
                elif state == vlc.State.Stopped:
                    self.is_playing = False
                elif state == vlc.State.Ended:
                    self.is_playing = False
                    logging.info("视频播放结束")

                if not self.seeking:
                    current_time = self.media_player.get_time() / 1000.0
                    duration = self.media_player.get_length() / 1000.0

                    if duration > 0:
                        self.progress.set(current_time)

                        current_str = self.format_time(current_time)
                        duration_str = self.format_time(duration)
                        self.time_label.config(text=f"{current_str} / {duration_str}")

            except Exception as e:
                logging.error(f"更新进度条时出错: {str(e)}")

        self.root.after(100, self.update_progress)

    def format_time(self, seconds):
        """格式化时间显示"""
        minutes = int(seconds // 60)
        seconds = int(seconds % 60)
        return f"{minutes:02d}:{seconds:02d}"

    def play(self):
        """开始播放"""
        if self.media_player is not None:
            try:
                self.media_player.play()
                self.is_playing = True
                logging.info("开始播放视频")
            except Exception as e:
                logging.error(f"播放视频时发生错误：{str(e)}")
                messagebox.showerror("错误", f"播放视频时发生错误：{str(e)}")

    def pause(self):
        """暂停播放"""
        if self.media_player is not None:
            try:
                self.media_player.pause()
                self.is_playing = False
                logging.info("暂停播放视频")
            except Exception as e:
                logging.error(f"暂停视频时发生错误：{str(e)}")

    def stop(self):
        """停止播放"""
        if self.media_player is not None:
            try:
                self.media_player.stop()
                self.is_playing = False
                self.progress.set(0)
                self.time_label.config(text="00:00 / 00:00")
                logging.info("停止播放视频")
            except Exception as e:
                logging.error(f"停止视频时发生错误：{str(e)}")

    def on_closing(self):
        """窗口关闭时的清理工作"""
        try:
            if self.media_player is not None:
                self.media_player.stop()
                self.media_player.release()
            if self.vlc_instance is not None:
                self.vlc_instance.release()
            logging.info("清理VLC资源完成")
        except Exception as e:
            logging.error(f"清理VLC资源时发生错误：{str(e)}")
        finally:
            self.root.destroy()

def main():
    """主函数"""
    if not os.path.exists(VIDEO_DIR):
        messagebox.showerror("错误", f"视频目录不存在：{VIDEO_DIR}")
        return

    if not os.path.exists(JSON_FILE):
        messagebox.showerror("错误", f"JSON文件不存在：{JSON_FILE}")
        return

    root = tk.Tk()
    app = VideoApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)

    try:
        root.iconbitmap(default='icon.ico')
    except:
        pass

    try:
        root.mainloop()
    except KeyboardInterrupt:
        logging.info("用户中断程序")
    except Exception as e:
        logging.error(f"程序运行时发生错误：{str(e)}")
        messagebox.showerror("错误", f"程序运行时发生错误：{str(e)}")
    finally:
        logging.info("程序结束")

if __name__ == "__main__":
    main()