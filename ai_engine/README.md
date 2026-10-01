# shopsathi_ai

Independent AI-engine package. It never imports `backend/`; shop data arrives only through the `ShopDataGateway` protocol (defined later) which the backend implements.

The `mock` providers are deterministic test doubles for automated tests, not AI.

```bash
pip install -e ".[dev]"
pytest
```
