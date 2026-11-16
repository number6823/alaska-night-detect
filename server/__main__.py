"""python -m server 로 기록 서버를 띄운다."""

import argparse

import uvicorn

from .app import create_app


def main() -> None:
    parser = argparse.ArgumentParser(prog="python -m server")
    parser.add_argument(
        "--host",
        default="127.0.0.1",
        help="같은 네트워크의 Jetson 이 올리려면 0.0.0.0 (로그인이 없으니 신뢰하는 네트워크에서만)",
    )
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--data", default="data/server", help="DB 와 캡처를 둘 폴더")
    parser.add_argument(
        "--web-dist", default="web/dist", help="빌드한 화면 폴더(있으면 같이 보여 준다)"
    )
    args = parser.parse_args()
    if args.host != "127.0.0.1":
        print("[주의] 로그인이 없다. 신뢰하는 네트워크 안에서만 연다.")
    uvicorn.run(create_app(args.data, args.web_dist), host=args.host, port=args.port)


if __name__ == "__main__":
    main()
