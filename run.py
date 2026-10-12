import os
import uvicorn
if __name__ == '__main__':
    from app.server import app
    concurrency = int(os.environ.get('TGTOP_CONCURRENCY', '32'))
    if concurrency < 2:
        raise ValueError('TGTOP_CONCURRENCY must be at least 2')
    uvicorn.run(app,host=os.environ.get('TGTOP_HOST','127.0.0.1'),port=int(os.environ.get('TGTOP_PORT','8765')),workers=1,limit_concurrency=concurrency,timeout_keep_alive=5,access_log=False,log_level='warning')
