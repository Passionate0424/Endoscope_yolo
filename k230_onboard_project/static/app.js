// 内窥镜检测平台前端控制脚本

class EndoscopeApp {
    constructor() {
        this.apiBase = '';  // API基础路径
        this.updateInterval = null;
        this.cameraRunning = false;
        this.detectionEnabled = false;
        this.lastStatusResult = null;  // 保存最后一次状态查询结果
        this._cachedRecords = [];

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

        // ⭐ 关键修复：页面加载时从服务器获取当前状态
        this.loadInitialState();
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

            // ⭐ 修复：先获取响应文本，如果JSON解析失败，可以显示原始响应
            const text = await response.text();
            try {
                return JSON.parse(text);
            } catch (jsonError) {
                // JSON解析失败，记录原始响应以便调试
                console.error(`[App] JSON解析失败 (${endpoint}):`, jsonError);
                console.error(`[App] 服务器原始响应:`, text.substring(0, 200));
                return { success: false, error: `Invalid JSON response: ${jsonError.message}` };
            }
        } catch (error) {
            console.error('API调用失败:', error);
            return { success: false, error: error.message };
        }
    }

    // 启动摄像头
    async startCamera() {
        const result = await this.apiCall('/api/camera/start', 'POST');
        console.log('[App] startCamera API 响应:', result);
        if (result.success) {
            // ⭐ 关键修复：不要立即设置状态，而是等待服务器状态同步
            // 因为摄像头启动是异步的，需要等待YOLO线程初始化
            this.showMessage('摄像头启动命令已发送，正在初始化...', 'success');

            // 立即刷新状态，然后定期检查直到状态同步
            let checkCount = 0;
            const maxChecks = 20; // 最多检查20次（约40秒，给YOLO线程更多初始化时间）
            let lastDesiredState = false;
            let pythonLayerNotRunning = false;

            const checkInterval = setInterval(() => {
                checkCount++;
                console.log(`[App] 检查摄像头状态 (${checkCount}/${maxChecks})，当前状态:`, this.cameraRunning);
                this.updateStats().then(() => {
                    // 检查 desired 状态，判断Python层是否响应
                    const statusResult = this.lastStatusResult;
                    if (statusResult && statusResult.data && statusResult.data.camera) {
                        const desired = statusResult.data.camera.desired === true ||
                            statusResult.data.camera.desired === 'true' ||
                            statusResult.data.camera.desired === 1 ||
                            statusResult.data.camera.desired === '1';
                        const running = statusResult.data.camera.running === true ||
                            statusResult.data.camera.running === 'true' ||
                            statusResult.data.camera.running === 1 ||
                            statusResult.data.camera.running === '1';

                        console.log(`[App] 状态检查完成 - desired: ${desired}, running: ${running}, 前端状态: ${this.cameraRunning}`);

                        // 如果 desired=true 但 running=false 持续多次，说明Python层可能没有运行
                        if (desired && !running && checkCount >= 5) {
                            if (!pythonLayerNotRunning) {
                                pythonLayerNotRunning = true;
                                this.showMessage('⚠️ Python层未响应，请确保已运行 main_rtsmart.py', 'warning');
                            }
                        }

                        lastDesiredState = desired;
                    }

                    console.log(`[App] 状态检查完成，摄像头运行状态:`, this.cameraRunning);
                    // 如果状态已同步，停止检查
                    if (this.cameraRunning || checkCount >= maxChecks) {
                        clearInterval(checkInterval);
                        if (this.cameraRunning) {
                            this.showMessage('摄像头已启动', 'success');
                        } else if (checkCount >= maxChecks) {
                            if (pythonLayerNotRunning) {
                                this.showMessage('摄像头启动超时：Python层未响应，请检查 main_rtsmart.py 是否正在运行', 'error');
                            } else {
                                this.showMessage('摄像头启动超时，请检查系统状态', 'error');
                            }
                        }
                    }
                }).catch((error) => {
                    console.error('[App] 状态检查失败:', error);
                });
            }, 2000); // 每2秒检查一次

            // 立即更新一次状态
            setTimeout(() => {
                console.log('[App] 立即检查一次状态...');
                this.updateStats().catch((error) => {
                    console.error('[App] 立即状态检查失败:', error);
                });
            }, 500);
        } else {
            this.showMessage('启动失败: ' + (result.message || '未知错误'), 'error');
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
            // ⭐ 立即刷新状态，确保同步
            setTimeout(() => this.updateStats(), 500);
        } else {
            this.showMessage('停止失败: ' + (result.message || '未知错误'), 'error');
        }
    }

    // 启用检测
    async enableDetection() {
        const result = await this.apiCall('/api/detection/enable', 'POST');
        if (result.success) {
            this.detectionEnabled = true;
            this.updateStatus();
            this.showMessage('检测已启用', 'success');
            // ⭐ 立即刷新状态，确保同步
            setTimeout(() => this.updateStats(), 500);
        } else {
            this.showMessage('启用失败: ' + (result.message || '未知错误'), 'error');
        }
    }

    // 禁用检测
    async disableDetection() {
        const result = await this.apiCall('/api/detection/disable', 'POST');
        if (result.success) {
            this.detectionEnabled = false;
            this.updateStatus();
            this.showMessage('检测已禁用', 'success');
            // ⭐ 立即刷新状态，确保同步
            setTimeout(() => this.updateStats(), 500);
        } else {
            this.showMessage('禁用失败: ' + (result.message || '未知错误'), 'error');
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
            // 先停止旧的流
            this.videoStream.src = '';
            this.videoStream.onerror = null;
            this.videoStream.onload = null;

            // 等待一小段时间确保旧连接关闭
            setTimeout(() => {
                // 添加时间戳防止缓存
                const timestamp = new Date().getTime();
                const streamUrl = `/stream?t=${timestamp}`;

                console.log('[App] 启动视频流:', streamUrl);
                this.videoStream.src = streamUrl;
                this.videoStream.style.display = 'block';
                this.videoPlaceholder.style.display = 'none';

                // 添加错误处理
                let errorCount = 0;
                const maxErrors = 3;

                this.videoStream.onerror = () => {
                    errorCount++;
                    console.error(`[App] 视频流加载失败 (${errorCount}/${maxErrors})`);

                    if (errorCount >= maxErrors) {
                        console.error('[App] 视频流多次失败，停止重试');
                        this.videoStream.style.display = 'none';
                        this.videoPlaceholder.style.display = 'flex';
                        this.videoPlaceholder.textContent = '视频流连接失败';
                    } else if (this.cameraRunning) {
                        // 只有在摄像头仍在运行时才重试
                        console.log('[App] 3秒后重试视频流...');
                        setTimeout(() => {
                            if (this.cameraRunning) {
                                this.updateVideoStream();
                            }
                        }, 3000);
                    }
                };

                // 成功加载第一帧
                this.videoStream.onload = () => {
                    if (errorCount > 0) {
                        console.log('[App] 视频流已恢复');
                        errorCount = 0;
                    }
                };
            }, 100);
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

    // 加载初始状态（页面刷新后恢复状态）
    async loadInitialState() {
        try {
            const result = await this.apiCall('/api/status');
            console.log('[App] 加载初始状态，服务器返回:', result);

            if (result.success && result.data) {
                const data = result.data;

                // ⭐ 关键修复：恢复摄像头状态 - 使用actual状态（这是Python层同步的真实状态）
                // 优先使用actual状态，如果没有则使用desired状态
                const cameraRunning = data.camera && (
                    data.camera.running === true ||
                    data.camera.running === 'true' ||
                    data.camera.running === 1 ||
                    data.camera.running === '1'
                );
                console.log('[App] 摄像头状态 - 服务器:', cameraRunning, '前端当前:', this.cameraRunning);

                // ⭐ 关键修复：无论状态是否变化，都要同步（确保页面刷新后状态正确）
                this.cameraRunning = cameraRunning;
                if (cameraRunning) {
                    console.log('[App] 恢复视频流（摄像头正在运行）');
                    // 延迟一下确保DOM就绪
                    setTimeout(() => this.updateVideoStream(), 200);
                } else {
                    console.log('[App] 摄像头未运行，停止视频流');
                    this.stopVideoStream();
                }

                // ⭐ 恢复检测状态 - 使用actual状态
                const detectionEnabled = data.detection && (
                    data.detection.enabled === true ||
                    data.detection.enabled === 'true' ||
                    data.detection.enabled === 1 ||
                    data.detection.enabled === '1'
                );
                if (detectionEnabled !== undefined) {
                    this.detectionEnabled = detectionEnabled;
                }

                // 恢复置信度
                if (data.confidence && data.confidence.actual !== undefined) {
                    const confValue = parseFloat(data.confidence.actual);
                    if (!isNaN(confValue)) {
                        const slider = document.getElementById('confidenceSlider');
                        const valueDisplay = document.getElementById('confidenceValue');
                        if (slider && valueDisplay) {
                            slider.value = Math.round(confValue * 100);
                            valueDisplay.textContent = confValue.toFixed(2);
                        }
                    }
                }

                // 更新UI状态
                this.updateStatus();

                // ⭐ 关键修复：更新统计数据 - 确保即使值为0也显示
                if (data.yolo_stats) {
                    const stats = data.yolo_stats;
                    const fpsEl = document.getElementById('statFps');
                    const detEl = document.getElementById('statDetections');
                    const framesEl = document.getElementById('statFrames');

                    // 确保FPS显示正确（即使为0也要显示）
                    if (fpsEl) {
                        const fpsValue = stats.fps !== undefined && stats.fps !== null ? parseFloat(stats.fps) : 0;
                        fpsEl.textContent = fpsValue.toFixed(1);
                    }
                    if (detEl) {
                        detEl.textContent = stats.total_detections !== undefined ? stats.total_detections : 0;
                    }
                    if (framesEl) {
                        framesEl.textContent = stats.total_frames !== undefined ? stats.total_frames : 0;
                    }
                }

                if (data.detection_stats) {
                    const records = data.detection_stats;
                    const recordsEl = document.getElementById('statRecords');
                    if (recordsEl) recordsEl.textContent = records.total_count !== undefined ? records.total_count : 0;
                }

                console.log('[App] ✅ 初始状态已恢复:', {
                    camera: this.cameraRunning,
                    detection: this.detectionEnabled,
                    stats: data.yolo_stats
                });
            } else {
                console.warn('[App] ⚠️ 无法加载初始状态，服务器返回:', result);
            }
        } catch (error) {
            console.error('[App] ❌ 加载初始状态失败:', error);
        }
    }

    // 更新统计信息
    async updateStats() {
        try {
            const result = await this.apiCall('/api/status');
            console.log('[App] updateStats API 响应:', result);
            // ⭐ 保存状态结果，供 startCamera() 检查 desired 状态
            this.lastStatusResult = result;
            if (result.success && result.data) {
                const data = result.data;
                console.log('[App] 状态数据:', JSON.stringify(data));

                // ⭐ 关键修复：更新统计数据 - 确保即使值为0也显示
                if (data.yolo_stats) {
                    const stats = data.yolo_stats;
                    const fpsEl = document.getElementById('statFps');
                    const detEl = document.getElementById('statDetections');
                    const framesEl = document.getElementById('statFrames');

                    // 确保FPS显示正确（即使为0也要显示）
                    if (fpsEl) {
                        const fpsValue = stats.fps !== undefined && stats.fps !== null ? parseFloat(stats.fps) : 0;
                        fpsEl.textContent = fpsValue.toFixed(1);
                    }
                    if (detEl) {
                        detEl.textContent = stats.total_detections !== undefined ? stats.total_detections : 0;
                    }
                    if (framesEl) {
                        framesEl.textContent = stats.total_frames !== undefined ? stats.total_frames : 0;
                    }
                }

                if (data.detection_stats) {
                    const records = data.detection_stats;
                    const recordsEl = document.getElementById('statRecords');
                    if (recordsEl) recordsEl.textContent = records.total_count !== undefined ? records.total_count : 0;
                }

                // ⭐ 关键修复：同步摄像头和检测状态（防止状态不同步）
                // 使用actual状态（running/enabled），这是Python层同步的真实状态
                if (data.camera) {
                    const cameraRunning = data.camera.running === true ||
                        data.camera.running === 'true' ||
                        data.camera.running === 1 ||
                        data.camera.running === '1';
                    console.log('[App] 解析摄像头状态 - 原始值:', data.camera.running, '解析后:', cameraRunning, '当前前端状态:', this.cameraRunning);
                    // ⭐ 关键修复：无论状态是否变化都要更新，确保 startCamera() 等待循环能检测到状态
                    const stateChanged = cameraRunning !== this.cameraRunning;
                    if (stateChanged) {
                        console.log('[App] 检测到摄像头状态变化:', this.cameraRunning, '->', cameraRunning);
                    }
                    this.cameraRunning = cameraRunning;
                    if (cameraRunning) {
                        if (stateChanged) {
                            console.log('[App] 摄像头已启动，更新视频流');
                            this.updateVideoStream();
                        }
                    } else {
                        if (stateChanged) {
                            console.log('[App] 摄像头已停止，停止视频流');
                            this.stopVideoStream();
                        }
                    }
                    if (stateChanged) {
                        this.updateStatus();
                    }
                } else {
                    console.log('[App] ⚠️ 状态数据中没有 camera 字段');
                }

                if (data.detection) {
                    const detectionEnabled = data.detection.enabled === true ||
                        data.detection.enabled === 'true' ||
                        data.detection.enabled === 1 ||
                        data.detection.enabled === '1';
                    if (detectionEnabled !== undefined && detectionEnabled !== this.detectionEnabled) {
                        console.log('[App] 检测到检测状态变化:', this.detectionEnabled, '->', detectionEnabled);
                        this.detectionEnabled = detectionEnabled;
                        this.updateStatus();
                    }
                }
            }
        } catch (error) {
            console.error('[App] 更新统计信息失败:', error);
        }
    }

    // 加载检测记录
    async loadRecords() {
        const result = await this.apiCall('/api/records?limit=20');
        if (result.success) {
            // 缓存记录，供查找/下载等操作使用
            try {
                this._cachedRecords = Array.isArray(result.data) ? result.data : [];
            } catch (e) {
                this._cachedRecords = [];
            }
            this.renderRecords(this._cachedRecords);
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
                    <img src="/detections/${encodeURIComponent(record.filename)}" class="detection-thumb" alt="检测图像">
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
            link.href = `/detections/${encodeURIComponent(record.filename)}`;
            link.download = record.filename;
            // Fallback: open in a new tab if browser ignores download attribute
            link.target = '_blank';
            link.rel = 'noopener';
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
        // ⭐ 优化：降低轮询频率以减少K230设备负载，但保持响应性
        // 使用2秒间隔，平衡响应速度和服务器压力
        this.updateInterval = setInterval(() => {
            this.updateStats();
            // 每30秒刷新一次记录
            if (Math.random() < 0.1) {
                this.loadRecords();
            }
        }, 2000);  // 2秒轮询间隔，提高状态同步速度
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
        if (!this._cachedRecords || !Array.isArray(this._cachedRecords)) return null;
        for (let i = 0; i < this._cachedRecords.length; i++) {
            const rec = this._cachedRecords[i];
            if (rec && (rec.id === id || String(rec.id) === String(id))) return rec;
        }
        return null;
    }
}

// 初始化应用
const app = new EndoscopeApp();
