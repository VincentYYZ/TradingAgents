# TradingAgents 完整分析报告（协鑫集成 - 002506）

## 任务信息
- 市场：cn_a_share
- 股票代码：002506
- 公司名称：协鑫集成
- 分析日期：2026-05-11
- LLM 提供商：lucen_openai

## 组合管理决策

## 错误详情

Connection error.

```text
Traceback (most recent call last):
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/httpx/_transports/default.py", line 101, in map_httpcore_exceptions
    yield
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/httpx/_transports/default.py", line 250, in handle_request
    resp = self._pool.handle_request(req)
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/httpcore/_sync/connection_pool.py", line 256, in handle_request
    raise exc from None
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/httpcore/_sync/connection_pool.py", line 236, in handle_request
    response = connection.handle_request(
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/httpcore/_sync/http_proxy.py", line 316, in handle_request
    stream = stream.start_tls(**kwargs)
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/httpcore/_sync/http11.py", line 376, in start_tls
    return self._stream.start_tls(ssl_context, server_hostname, timeout)
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/httpcore/_backends/sync.py", line 154, in start_tls
    with map_exceptions(exc_map):
  File "/usr/lib/python3.10/contextlib.py", line 153, in __exit__
    self.gen.throw(typ, value, traceback)
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/httpcore/_exceptions.py", line 14, in map_exceptions
    raise to_exc(exc) from exc
httpcore.ConnectError: [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1007)

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/openai/_base_client.py", line 1037, in request
    response = self._send_request(
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/openai/_client.py", line 440, in _send_request
    return self._send_with_auth_retry(request, stream=stream, **kwargs)
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/openai/_client.py", line 418, in _send_with_auth_retry
    response = super()._send_request(request, stream=stream, **kwargs)
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/openai/_base_client.py", line 964, in _send_request
    return self._client.send(request, stream=stream, **kwargs)
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/httpx/_client.py", line 914, in send
    response = self._send_handling_auth(
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/httpx/_client.py", line 942, in _send_handling_auth
    response = self._send_handling_redirects(
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/httpx/_client.py", line 979, in _send_handling_redirects
    response = self._send_single_request(request)
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/httpx/_client.py", line 1014, in _send_single_request
    response = transport.handle_request(request)
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/httpx/_transports/default.py", line 249, in handle_request
    with map_httpcore_exceptions():
  File "/usr/lib/python3.10/contextlib.py", line 153, in __exit__
    self.gen.throw(typ, value, traceback)
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/httpx/_transports/default.py", line 118, in map_httpcore_exceptions
    raise mapped_exc(message) from exc
httpx.ConnectError: [SSL: UNEXPECTED_EOF_WHILE_READING] EOF occurred in violation of protocol (_ssl.c:1007)

The above exception was the direct cause of the following exception:

Traceback (most recent call last):
  File "/mnt/Uptec777/Projects/TradingAgents/gradio_app.py", line 1118, in _run_single_analysis
    for chunk in graph.graph.stream(init_state, **args):
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/langgraph/pregel/main.py", line 2759, in stream
    for _ in runner.tick(
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/langgraph/pregel/_runner.py", line 167, in tick
    run_with_retry(
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/langgraph/pregel/_retry.py", line 126, in run_with_retry
    return task.proc.invoke(task.input, config)
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/langgraph/_internal/_runnable.py", line 656, in invoke
    input = context.run(step.invoke, input, config, **kwargs)
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/langgraph/_internal/_runnable.py", line 400, in invoke
    ret = self.func(*args, **kwargs)
  File "/mnt/Uptec777/Projects/TradingAgents/tradingagents/agents/analysts/market_analyst.py", line 74, in market_analyst_node
    result = chain.invoke(state["messages"])
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/langchain_core/runnables/base.py", line 3215, in invoke
    input_ = context.run(step.invoke, input_, config)
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/langchain_core/runnables/base.py", line 5753, in invoke
    return self.bound.invoke(
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/langchain_core/language_models/chat_models.py", line 472, in invoke
    self.generate_prompt(
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/langchain_core/language_models/chat_models.py", line 1752, in generate_prompt
    return self.generate(prompt_messages, stop=stop, callbacks=callbacks, **kwargs)
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/langchain_core/language_models/chat_models.py", line 1559, in generate
    self._generate_with_cache(
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/langchain_core/language_models/chat_models.py", line 1899, in _generate_with_cache
    result = self._generate(
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/langchain_openai/chat_models/base.py", line 1655, in _generate
    _handle_openai_api_error(e)
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/langchain_openai/chat_models/base.py", line 1650, in _generate
    raw_response = self.client.with_raw_response.create(**payload)
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/openai/_legacy_response.py", line 367, in wrapped
    return cast(LegacyAPIResponse[R], func(*args, **kwargs))
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/openai/_utils/_utils.py", line 298, in wrapper
    return func(*args, **kwargs)
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/openai/resources/chat/completions/completions.py", line 1215, in create
    return self._post(
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/openai/_base_client.py", line 1332, in post
    return cast(ResponseT, self.request(cast_to, opts, stream=stream, stream_cls=stream_cls))
  File "/mnt/Uptec777/Projects/TradingAgents/venv/lib/python3.10/site-packages/openai/_base_client.py", line 1072, in request
    raise APIConnectionError(request=request) from err
openai.APIConnectionError: Connection error.

```