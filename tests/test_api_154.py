import json

import httpx
import pytest
import respx

import adanos_cli.config as cli_config
import adanos_cli.main as cli_main


@pytest.mark.parametrize(
    ("base_url", "target", "status"),
    [
        (None, None, 200),
        (None, "Apple", 200),
        ("https://api.adanos.org", "Apple", 200),
        (None, "Apple", 422),
    ],
)
@respx.mock
def test_sentiment_request_through_cli(base_url, target, status, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli_config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cli_config, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(cli_config, "CREDENTIALS_PATH", tmp_path / "credentials.json")
    monkeypatch.setenv("ADANOS_API_KEY", "adanos_key_test")
    monkeypatch.delenv("ADANOS_BASE_URL", raising=False)
    response = (
        {"sentiment_label": "positive", "components": {"engine_version": "5.5", "model_score": None}}
        if status == 200
        else {"detail": "Invalid target"}
    )
    route = respx.post(f"{base_url or 'https://api.adanos.com'}/sentiment/v1/analyze").mock(
        return_value=httpx.Response(status, json=response)
    )
    argv = ["--json", "endpoint", "call", "sentiment.analyze", "--text", "Apple beats estimates"]
    if base_url is not None:
        argv += ["--base-url", base_url]
    if target is not None:
        argv += ["--target", target]

    result = cli_main.main(argv)
    captured = capsys.readouterr()

    assert route.call_count == 1
    request = route.calls[0].request
    body = {"text": "Apple beats estimates"}
    if target is not None:
        body["target"] = target
    assert json.loads(request.content) == body
    assert request.headers["X-API-Key"] == "adanos_key_test"
    if status == 200:
        assert result == 0
        assert json.loads(captured.out)["data"] == response
    else:
        assert result == 1
        assert json.loads(captured.err)["error"]["status_code"] == 422
    (tmp_path / "request-artifact.json").write_text(
        json.dumps({"argv": argv, "request": body, "status": status, "exit_code": result}, indent=2)
    )


def test_target_is_rejected_for_other_endpoints(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli_config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(cli_config, "CONFIG_PATH", tmp_path / "config.json")
    monkeypatch.setattr(cli_config, "CREDENTIALS_PATH", tmp_path / "credentials.json")
    argv = ["--json", "endpoint", "call", "root.health", "--target", "Apple"]
    result = cli_main.main(argv)
    captured = capsys.readouterr()
    assert result == 2
    assert json.loads(captured.err)["error"]["message"] == "Endpoint root.health does not support --target"
    (tmp_path / "request-artifact.json").write_text(json.dumps({"argv": argv, "exit_code": result}, indent=2))
