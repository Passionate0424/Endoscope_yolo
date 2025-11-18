// 内窥镜检测平台前端控制脚本

class EndoscopeApp {
    constructor() {
        this.apiBase = '';  // API基础路径
        this.updateInterval = null;
        this.cameraRunning = false;
        this.detectionEnabled = false;

        this.init();
    }

    init() {
        // 绑定UI元素
        this.videoStream = document.getElementById('videoStream');
        this.videoPlaceholder = document.getElementById('videoPlaceholder');
        this.statusIndicator = document.getElementById('statusIndicator');

        // 绑定按钮事件
        document.getElementById('btnStartCamera').addEventListener('click', () => this.startCamera());
        document.getElementById('btnStopCamera').addEventListener('click', () => this.stopCamera());
        document.getElementById('btnEnableDetection').addEventListener('click', () => this.enableDetection());
        document.getElementById('btnDisableDetection').addEventListener('click', () => this.disableDetection());
        document.getElementById('btnRefreshRecords').addEventListener('click', () => this.loadRecords());
        document.getElementById('btnClearRecords').addEventListener('click', () => this.clearRecords());

        // 置信度滑块
        const slider = document.getElementById('confidenceSlider');
        slider.addEventListener('input', (e) => {
            const value = e.target.value / 100;
            document.getElementById('confidenceValue').textContent = value.toFixed(2);
        });
        slider.addEventListener('change', (e) => {
            const value = e.target.value / 100;
            this.setConfidence(value);
        });

        // 启动定时更新
        this.startAutoUpdate();

        // 加载初始数据
        this.loadRecords();
    }

    // API调用方法
    async apiCall(endpoint, method = 'GET', data = null) {
        try {
            const options = {
                method: method,
                headers: {
                    'Content-Type': 'application/json'
                }
            };

            if (data && method === 'POST') {
                options.body = JSON.stringify(data);
            }

            const response = await fetch(this.apiBase + endpoint, options);
            return await response.json();
        } catch (error) {
            console.error('API调用失败:', error);
            return { success: false, error: error.message };
        }
    }

    // 启动摄像头
    async startCamera() {
        const result = await this.apiCall('/api/camera/start', 'POST');
        if (result.success) {
            this.cameraRunning = true;
            this.updateVideoStream();
            this.updateStatus();
            this.showMessage('摄像头已启动', 'success');
        } else {
            this.showMessage('启动失败: ' + result.message, 'error');
        }
    }

    // 停止摄像头
    async stopCamera() {
        const result = await this.apiCall('/api/camera/stop', 'POST');
        if (result.success) {
            this.cameraRunning = false;
            this.stopVideoStream();
            this.updateStatus();
            this.showMessage('摄像头已停止', 'success');
        } else {
            this.showMessage('停止失败: ' + result.message, 'error');
        }
    }

    // 启用检测
    async enableDetection() {
        const result = await this.apiCall('/api/detection/enable', 'POST');
        if (result.success) {
            this.detectionEnabled = true;
            this.updateStatus();
            this.showMessage('检测已启用', 'success');
        } else {
            this.showMessage('启用失败: ' + result.message, 'error');
        }
    }

    // 禁用检测
    async disableDetection() {
        const result = await this.apiCall('/api/detection/disable', 'POST');
        if (result.success) {
            this.detectionEnabled = false;
            this.updateStatus();
            this.showMessage('检测已禁用', 'success');
        } else {
            this.showMessage('禁用失败: ' + result.message, 'error');
        }
    }

    // 设置置信度阈值
    async setConfidence(value) {
        const result = await this.apiCall('/api/config/confidence', 'POST', { value: value });
        if (result.success) {
            this.showMessage(`置信度已设置为 ${value.toFixed(2)}`, 'success');
        }
    }

    // 更新视频流
    updateVideoStream() {
        if (this.cameraRunning) {
            // 添加时间戳防止缓存，并添加错误处理
            const timestamp = new Date().getTime();
            this.videoStream.src = `/stream?t=${timestamp}`;
            this.videoStream.style.display = 'block';
            this.videoPlaceholder.style.display = 'none';

            // 添加错误处理，防止无限重连
            this.videoStream.onerror = () => {
                console.error('视频流加载失败');
                // 不要立即重试，避免无限循环
            };
        }
    }

    // 停止视频流
    stopVideoStream() {
        this.videoStream.onerror = null;  // 移除错误处理器
        this.videoStream.src = '';
        this.videoStream.style.display = 'none';
        this.videoPlaceholder.style.display = 'flex';
        this.videoPlaceholder.textContent = '摄像头未启动';
    }

    // 更新状态指示器
    updateStatus() {
        if (this.cameraRunning) {
            this.statusIndicator.textContent = this.detectionEnabled ? '检测中' : '运行中';
            this.statusIndicator.className = 'status-indicator active';
        } else {
            this.statusIndicator.textContent = '离线';
            this.statusIndicator.className = 'status-indicator inactive';
        }
    }

    // 更新统计信息
    async updateStats() {
        const result = await this.apiCall('/api/status');
        if (result.success) {
            const stats = result.data.yolo_stats;
            document.getElementById('statFps').textContent = stats.fps.toFixed(1);
            document.getElementById('statDetections').textContent = stats.total_detections;
            document.getElementById('statFrames').textContent = stats.total_frames;

            const records = result.data.detection_stats;
            document.getElementById('statRecords').textContent = records.total_count;
        }
    }

    // 加载检测记录
    async loadRecords() {
        const result = await this.apiCall('/api/records?limit=20');
        if (result.success) {
            this.renderRecords(result.data);
        }
    }

    // 渲染检测记录
    renderRecords(records) {
        const listContainer = document.getElementById('detectionList');

        if (!records || records.length === 0) {
            listContainer.innerHTML = '<div class="empty-state">暂无检测记录</div>';
            return;
        }

        let html = '';
        records.forEach(record => {
            const confidence = (record.confidence * 100).toFixed(1);
            html += `
                <div class="detection-item" data-id="${record.id}">
                    <img src="/detections/${record.filename}" class="detection-thumb" alt="检测图像">
                    <div class="detection-info">
                        <div class="detection-time">${record.time_str}</div>
                        <span class="detection-confidence">置信度: ${confidence}%</span>
                    </div>
                    <div class="detection-actions">
                        <button class="btn-primary btn-small" onclick="app.downloadRecord(${record.id})">下载</button>
                        <button class="btn-danger btn-small" onclick="app.deleteRecord(${record.id})">删除</button>
                    </div>
                </div>
            `;
        });

        listContainer.innerHTML = html;
    }

    // 下载记录
    downloadRecord(id) {
        // 通过链接下载
        const record = this.findRecord(id);
        if (record) {
            const link = document.createElement('a');
            link.href = `/detections/${record.filename}`;
            link.download = record.filename;
            link.click();
        }
    }

    // 删除记录
    async deleteRecord(id) {
        if (!confirm('确定要删除这条记录吗？')) {
            return;
        }

        const result = await this.apiCall(`/api/records/${id}`, 'DELETE');
        if (result.success) {
            this.showMessage('记录已删除', 'success');
            this.loadRecords();
        } else {
            this.showMessage('删除失败: ' + result.message, 'error');
        }
    }

    // 清空所有记录
    async clearRecords() {
        if (!confirm('确定要清空所有记录吗？此操作不可恢复！')) {
            return;
        }

        const result = await this.apiCall('/api/records/clear', 'POST');
        if (result.success) {
            this.showMessage('所有记录已清空', 'success');
            this.loadRecords();
        } else {
            this.showMessage('清空失败: ' + result.message, 'error');
        }
    }

    // 启动自动更新
    startAutoUpdate() {
        // 降低轮询频率以减少K230设备负载
        // 从3秒进一步增加到5秒，大幅减少服务器压力
        this.updateInterval = setInterval(() => {
            this.updateStats();
            // 每30秒刷新一次记录（原来是每10秒）
            if (Math.random() < 0.1) {
                this.loadRecords();
            }
        }, 5000);  // 5秒轮询间隔
    }

    // 显示消息提示
    showMessage(message, type = 'info') {
        // 简单的控制台输出，可以替换为更友好的UI提示
        console.log(`[${type}] ${message}`);

        // 可以添加toast提示组件
        // 这里简化处理
        if (type === 'error') {
            alert(message);
        }
    }

    // 查找记录（缓存）
    findRecord(id) {
        // 这里简化处理，实际应该从API获取
        return null;
    }
}

// 初始化应用
const app = new EndoscopeApp();
