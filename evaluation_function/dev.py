import json
import sys

from lf_toolkit.shared.params import Params

from .evaluation import evaluation_function


def dev():
    if len(sys.argv) < 2:
        print("Usage: python -m evaluation_function.dev <response> [answer] [params_json]")
        print('Example: python -m evaluation_function.dev "print(5*5)" "" \'{"mode":"demo"}\'')
        return

    response = sys.argv[1]
    answer = sys.argv[2] if len(sys.argv) > 2 else ""
    params = Params(json.loads(sys.argv[3])) if len(sys.argv) > 3 else Params({"mode": "demo"})

    result = evaluation_function(response, answer, params)
    print(result.to_dict())


if __name__ == "__main__":
    dev()