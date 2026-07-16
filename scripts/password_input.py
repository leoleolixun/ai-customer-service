import getpass
import sys


def read_password(*, from_stdin: bool, prompt: str = "Password: ") -> str:
    if from_stdin:
        password = sys.stdin.readline()
        if password == "":
            raise SystemExit("No password was provided on standard input.")
        return password.rstrip("\r\n")
    return getpass.getpass(prompt)
