<p align="center">
  <a href="https://fastapi.example.org"><img src="https://fastapi.example.org/img/logo.png" alt="Logo"></a>
</p>
<p align="center">
    <em>A web framework written for this test, quick to learn and ready for production.</em>
</p>
<p align="center">
<a href="https://github.com/fastapi/fastapi/actions?query=workflow%3ATest" target="_blank">
    <img src="https://github.com/fastapi/fastapi/actions/workflows/test.yml/badge.svg" alt="Test">
</a>
</p>

[![Coverage][coverage-badge]][coverage] [![Package](https://img.shields.io/pypi/v/example.svg)](https://pypi.org/project/example)

---

**Documentation**: <a href="https://fastapi.example.org" target="_blank">https://fastapi.example.org</a>

---

FastAPI is a web framework for building APIs with Python, based on standard Python type hints.

<!-- sponsors -->
<a href="https://sponsor.example.org" target="_blank" title="A sponsor"><img src="https://sponsor.example.org/logo.svg"></a>
<!-- /sponsors -->

## Opinions

"_I use it for every new service of my team._" — Jane Doe, @jane-doe, jane.doe@example.org

## Requirements

FastAPI stands on the shoulders of two libraries, Starlette for the web parts and Pydantic for the data parts.

## Installation

```console
$ pip install "fastapi[standard]"
```

    $ uvicorn main:app --reload

## Example

```python
from fastapi import FastAPI

app = FastAPI()
```

![Screenshot][screenshot]

## License

This project is licensed under the terms of the MIT license.

[coverage-badge]: https://coverage.example.org/badge.svg
[coverage]: https://coverage.example.org
[screenshot]: https://fastapi.example.org/img/screenshot.png
