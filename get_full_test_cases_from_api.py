"""
This module provides functions to interact with an API and retrieve full test cases and shared steps from a project.
It includes functions to make API requests, retrieve test cases and shared steps, expand shared steps, and more.

The module also includes a command-line interface (CLI) for requesting and retrieving full test cases.

e.g. print expanded human_readable_steps of test cases with test_case_number 1, 2 in the project:
```shell
python3 get_full_test_cases_from_api.py -t XXX -o Magicpod -p BrowserProject 1 2 |
  jq '.[].human_readable_steps' |
  python3 -c 'import sys, json; [print(json.loads(l)) for l in sys.stdin]'
```
"""

import argparse
import json
import logging
import re
import textwrap
import urllib.error
import urllib.request
from urllib.parse import urlencode

logging.basicConfig(
    format="[%(levelname)s - %(asctime)19.19s - %(module)s:%(lineno)d] %(message)s"
)
logger = logging.getLogger(__name__)


class MagicPodAPIClient:
    BASE_URL = "https://app.magicpod.com/api/v1.0"

    def __init__(self, token, locale):
        self.token = token
        self.locale = locale

    def get_shared_steps(self, organization_name, project_name, params=None):
        url = f"{self.BASE_URL}/{organization_name}/{project_name}/shared-steps/"
        return self._make_api_request(url, params)

    def get_shared_step(
        self, organization_name, project_name, shared_step_number, params=None
    ):
        url = f"{self.BASE_URL}/{organization_name}/{project_name}/shared-steps/{shared_step_number}/"
        return self._make_api_request(url, params)

    def get_test_cases(self, organization_name, project_name, params=None):
        url = f"{self.BASE_URL}/{organization_name}/{project_name}/test-cases/"
        return self._make_api_request(url, params)

    def get_test_case(
        self, organization_name, project_name, test_case_number, params=None
    ):
        url = f"{self.BASE_URL}/{organization_name}/{project_name}/test-cases/{test_case_number}/"
        return self._make_api_request(url, params)

    def _make_api_request(self, url, params=None):
        if params:
            query_string = urlencode(params)
            url = f"{url}?{query_string}"

        headers = {
            "Authorization": f"Token {self.token}",
            "Content-Type": "application/json",
            "Accept-Language": self.locale,
        }

        logger.debug(f"Request: {url}")
        request = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(request) as response:
                response_data = response.read()
                return {"error": False, "data": json.loads(response_data)}
        except urllib.error.HTTPError as e:
            return {"error": True, "message": f"Error: {url} - {e.code} - {e.reason}"}
        except Exception as e:
            return {"error": True, "message": f"Error: {url} - {str(e)}"}


class CustomMagicPodAPIClient(MagicPodAPIClient):
    def get_full_shared_steps(self, organization_name, project_name):
        """Get all full shared steps in the project."""
        all_shared_steps = []
        min_shared_step_number = 1
        while True:
            res = self.get_shared_steps(
                organization_name,
                project_name,
                params={"min_shared_step_number": min_shared_step_number},
            )
            if res["error"]:
                return res

            shared_steps = res["data"]["shared_steps"]
            if len(shared_steps) <= 0:
                break

            all_shared_steps.extend(shared_steps)
            min_shared_step_number = shared_steps[-1]["number"] + 1
        shared_step_numbers = [s["number"] for s in all_shared_steps]

        shared_steps = []
        for shared_step_number in shared_step_numbers:
            res = self.get_shared_step(
                organization_name, project_name, shared_step_number
            )
            if res["error"]:
                return res

            shared_steps.append(res["data"])

        return {"error": False, "data": shared_steps}

    def get_full_test_cases(
        self, organization_name, project_name, test_case_numbers=None
    ):
        """
        Get all full test cases in the project.
        If `test_case_numbers` is provided, only those test cases are retrieved.
        """
        if test_case_numbers is None:
            all_test_cases = []
            min_test_case_number = 1
            while True:
                res = self.get_test_cases(
                    organization_name,
                    project_name,
                    params={"min_test_case_number": min_test_case_number},
                )
                if res["error"]:
                    return res

                test_cases = res["data"]["test_cases"]
                if len(test_cases) <= 0:
                    break

                all_test_cases.extend(test_cases)
                min_test_case_number = test_cases[-1]["number"] + 1
            test_case_numbers = [t["number"] for t in all_test_cases]

        test_cases = []
        for test_case_number in test_case_numbers:
            res = self.get_test_case(organization_name, project_name, test_case_number)
            if res["error"]:
                return res

            test_cases.append(res["data"])

        return {"error": False, "data": test_cases}


# ==== Shared Steps Expander ==== #
def human_readable_steps_with_shared_steps_expanded(
    human_readable_steps, shared_step_name_map
):
    """Returns the human readable steps with shared steps expanded."""
    res = ""
    for step in human_readable_steps.splitlines():
        res += f"{step}\n"

        shared_step_name = extract_shared_step_name(step)
        if shared_step_name != "":
            indent = 2 + len(step) - len(step.lstrip())
            res += expand_shared_step(shared_step_name, shared_step_name_map, indent)

    return res


def extract_shared_step_name(step):
    """Extract shared step name from a shared step."""
    prefixes = ["Shared step:", "共有ステップ:"]
    s = step.strip()

    for prefix in prefixes:
        if s.startswith(prefix):
            return s.replace(prefix, "", 1)
    return ""


def expand_shared_step(shared_step_name, shared_step_name_map, indent):
    """Expand a shared step into its human readable steps."""
    for shared_step_name_candidate in shared_step_name_candidate_iterator(
        shared_step_name
    ):
        if shared_step_name_candidate not in shared_step_name_map:
            continue

        shared_step = shared_step_name_map[shared_step_name_candidate]
        return textwrap.indent(
            human_readable_steps_with_shared_steps_expanded(
                shared_step["human_readable_steps"], shared_step_name_map
            ),
            " " * indent,
        )
    return ""


def shared_step_name_candidate_iterator(shared_step_name):
    """
    Generate a sequence of candidate names by iteratively removing the last
    parenthetical group from the shared step name.

    For example, given the input "Login (2) (email: xxx.com, password: 123456)",
    this function yields:
    1. "Login (2) (email: xxx.com, password: 123456)"
    2. "Login (2)"
    3. "Login"
    """
    pattern = r"\(.*\)$"
    current_text = shared_step_name

    yield current_text.strip()

    while re.search(pattern, current_text):
        current_text = re.sub(pattern, "", current_text)
        yield current_text.strip()


# ==== Calculate Total Steps ==== #
def calculate_total_step_count(expanded_human_readable_steps):
    """
    Calculate total steps based on the length of the human readable steps.
    NOTE: This is an unofficial calculation way, and the value may be incorrect.
    """
    return len(
        [
            step
            for step in expanded_human_readable_steps.splitlines()
            if extract_shared_step_name(step) == ""
        ]
    )


# ==== CLI ==== #
def main():
    parser = argparse.ArgumentParser(description="CLI to request get full test cases")
    parser.add_argument("-t", "--token", required=True, help="API token")
    parser.add_argument("-o", "--organization", required=True, help="Organization name")
    parser.add_argument("-p", "--project", required=True, help="Project name")
    parser.add_argument(
        "test_case_numbers",
        nargs="*",
        type=int,
        help="If specified, only test cases with that numbers are retrieved.",
    )
    parser.add_argument(
        "-l",
        "--locale",
        default="ja",
        choices=["en", "ja"],
        required=False,
        help="Locale. It mainly affects the language of human_readable_steps.",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", default=False, help="Verbose mode"
    )
    args = parser.parse_args()
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    _main(
        args.token,
        args.organization,
        args.project,
        args.test_case_numbers if args.test_case_numbers else None,
        args.locale,
    )


def _main(token, organization_name, project_name, test_case_numbers, locale):
    client = CustomMagicPodAPIClient(token=token, locale=locale)
    res = client.get_full_shared_steps(organization_name, project_name)
    if res["error"]:
        logger.error(res["message"])
        exit(1)
    shared_steps = res["data"]

    res = client.get_full_test_cases(organization_name, project_name, test_case_numbers)
    if res["error"]:
        logger.error(res["message"])
        exit(1)
    test_cases = res["data"]

    shared_step_name_map = {
        shared_step["name"]: shared_step for shared_step in shared_steps
    }
    for test_case in test_cases:
        test_case["human_readable_steps"] = (
            human_readable_steps_with_shared_steps_expanded(
                test_case["human_readable_steps"], shared_step_name_map
            )
        )
        test_case["total_step_count"] = calculate_total_step_count(
            test_case["human_readable_steps"]
        )

    print(json.dumps(test_cases, ensure_ascii=False))


if __name__ == "__main__":
    main()
