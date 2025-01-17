// API 请求封装
const api = {
    baseURL: '/api',

    async request(method, url, data = null) {
        try {
            const config = {
                method,
                headers: {
                    'Content-Type': 'application/json'
                }
            };

            if (data && (method === 'POST' || method === 'PUT')) {
                config.body = JSON.stringify(data);
            }

            const response = await fetch(this.baseURL + url, config);
            if (!response.ok) {
                throw await response.json();
            }
            return await response.json();
        } catch (error) {
            ElMessage.error(error.detail || 'Request failed');
            throw error;
        }
    },

    getTasks() {
        return this.request('GET', '/tasks/');
    },

    createTask(data) {
        return this.request('POST', '/tasks/', data);
    },

    updateTask(id, data) {
        return this.request('PUT', `/tasks/${id}`, data);
    },

    deleteTask(id) {
        return this.request('DELETE', `/tasks/${id}`);
    },

    executeTask(id) {
        return this.request('POST', `/tasks/${id}/execute`);
    },

    getTaskHistory(id) {
        return this.request('GET', `/tasks/${id}/history`);
    }
};

// Vue 应用
const { createApp, ref, onMounted, reactive } = Vue;

const app = createApp({
    setup() {
        // 数据定义
        const tasks = ref([]);
        const taskHistory = ref([]);
        const selectedTask = ref(null);
        const dialogVisible = ref(false);
        const isEdit = ref(false);
        const loading = ref(false);

        // 表单数据
        const taskForm = reactive({
            name: '',
            description: '',
            script_path: '',
            schedule_type: 'interval',
            schedule_config: '',
            is_active: true
        });

        // 调度类型选项
        const scheduleTypes = [
            { value: 'interval', label: 'Interval' },
            { value: 'cron', label: 'Cron Expression' },
            { value: 'fixed', label: 'Fixed Time' }
        ];

        // 加载任务列表
        const loadTasks = async () => {
            try {
                loading.value = true;
                tasks.value = await api.getTasks();
            } catch (error) {
                console.error('Failed to load tasks:', error);
            } finally {
                loading.value = false;
            }
        };

        // 加载任务历史
        const loadTaskHistory = async (taskId) => {
            try {
                taskHistory.value = await api.getTaskHistory(taskId);
            } catch (error) {
                console.error('Failed to load task history:', error);
            }
        };

        // 创建/编辑任务对话框
        const showCreateDialog = () => {
            isEdit.value = false;
            Object.assign(taskForm, {
                name: '',
                description: '',
                script_path: '',
                schedule_type: 'interval',
                schedule_config: '',
                is_active: true
            });
            dialogVisible.value = true;
        };

        const showEditDialog = (task) => {
            isEdit.value = true;
            Object.assign(taskForm, task);
            dialogVisible.value = true;
        };

        // 保存任务
        const saveTask = async () => {
            try {
                loading.value = true;
                if (isEdit.value) {
                    await api.updateTask(selectedTask.value.id, taskForm);
                    ElMessage.success('Task updated successfully');
                } else {
                    await api.createTask(taskForm);
                    ElMessage.success('Task created successfully');
                }
                dialogVisible.value = false;
                await loadTasks();
            } catch (error) {
                console.error('Failed to save task:', error);
            } finally {
                loading.value = false;
            }
        };

        // 删除任务
        const deleteTask = async (task) => {
            try {
                await ElMessageBox.confirm(
                    'Are you sure to delete this task?',
                    'Warning',
                    {
                        confirmButtonText: 'OK',
                        cancelButtonText: 'Cancel',
                        type: 'warning'
                    }
                );

                await api.deleteTask(task.id);
                ElMessage.success('Task deleted successfully');
                await loadTasks();

                if (selectedTask.value?.id === task.id) {
                    selectedTask.value = null;
                    taskHistory.value = [];
                }
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('Failed to delete task:', error);
                }
            }
        };

        // 执行任务
        const executeTask = async (task) => {
            try {
                await api.executeTask(task.id);
                ElMessage.success('Task execution started');
                if (selectedTask.value?.id === task.id) {
                    setTimeout(() => loadTaskHistory(task.id), 1000);
                }
            } catch (error) {
                console.error('Failed to execute task:', error);
            }
        };

        // 选择任务
        const selectTask = (task) => {
            selectedTask.value = task;
            loadTaskHistory(task.id);
        };

        // 格式化时间
        const formatDateTime = (dateStr) => {
            if (!dateStr) return '-';
            const date = new Date(dateStr);
            return date.toLocaleString();
        };

        // 格式化状态
        const formatStatus = (status) => {
            const statusMap = {
                success: 'success',
                failed: 'danger',
                running: 'warning',
                timeout: 'info'
            };
            return statusMap[status] || 'info';
        };

        // 生命周期钩子
        onMounted(() => {
            loadTasks();
        });

        return {
            tasks,
            taskHistory,
            selectedTask,
            dialogVisible,
            isEdit,
            loading,
            taskForm,
            scheduleTypes,
            showCreateDialog,
            showEditDialog,
            saveTask,
            deleteTask,
            executeTask,
            selectTask,
            formatDateTime,
            formatStatus
        };
    }
});

// 挂载应用
app.use(ElementPlus);
app.mount('#app');