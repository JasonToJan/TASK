import os
from app import create_app, db

# 打印当前的 Python 路径
import sys
print("Python path:", sys.path)

app = create_app('development')

# 验证配置是否正确加载
print("App config:", app.config)

@app.route('/')
def index():
    return 'Hello, Flask!'

if __name__ == '__main__':
    app.run(host="0.0.0.0", port=5001, debug=True)
