"""autoSolve 服务端启动入口。"""

from app import app


if __name__ == "__main__":
    # Playwright sync API 不能跨线程复用；题目请求必须串行进入同一浏览器线程。
    app.run(host="127.0.0.1", port=8080, debug=False, threaded=False, use_reloader=False)
