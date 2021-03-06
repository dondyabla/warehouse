# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from unittest import mock

import pretend
import pytest

from pyramid.tweens import EXCVIEW, INGRESS
from whitenoise import WhiteNoise

from warehouse import static


class TestWhitenoiseTween:

    @pytest.mark.parametrize("autorefresh", [True, False])
    def test_bypasses(self, autorefresh):
        whitenoise = WhiteNoise(None, autorefresh=autorefresh)
        whitenoise.add_files(
            static.resolver.resolve("warehouse:/static/dist/").abspath(),
            prefix="/static/",
        )

        response = pretend.stub()
        handler = pretend.call_recorder(lambda request: response)
        registry = pretend.stub(whitenoise=whitenoise)

        request = pretend.stub(path_info="/other/", registry=registry)

        tween = static.whitenoise_tween_factory(handler, registry)
        resp = tween(request)

        assert resp is response

    @pytest.mark.parametrize("autorefresh", [True, False])
    def test_method_not_allowed(self, autorefresh):
        whitenoise = WhiteNoise(None, autorefresh=autorefresh)
        whitenoise.add_files(
            static.resolver.resolve("warehouse:/static/dist/").abspath(),
            prefix="/static/",
        )

        response = pretend.stub()
        handler = pretend.call_recorder(lambda request: response)
        registry = pretend.stub(whitenoise=whitenoise)

        request = pretend.stub(
            method="POST",
            environ={"HTTP_ACCEPT_ENCODING": "gzip"},
            path_info="/static/manifest.json",
            registry=registry,
        )

        tween = static.whitenoise_tween_factory(handler, registry)
        resp = tween(request)

        assert resp.status_code == 405

    def test_serves(self):
        whitenoise = WhiteNoise(None, autorefresh=True)
        whitenoise.add_files(
            static.resolver.resolve("warehouse:/static/dist/").abspath(),
            prefix="/static/",
        )

        path, headers = (whitenoise.find_file("/static/manifest.json")
                                   .get_path_and_headers({}))
        headers = dict(headers)

        response = pretend.stub()
        handler = pretend.call_recorder(lambda request: response)
        registry = pretend.stub(whitenoise=whitenoise)

        request = pretend.stub(
            method="GET",
            environ={},
            path_info="/static/manifest.json",
            registry=registry,
        )

        tween = static.whitenoise_tween_factory(handler, registry)
        resp = tween(request)

        assert resp.status_code == 200
        assert resp.headers["Content-Type"] == "application/json"
        assert resp.headers["Cache-Control"] == "public, max-age=60"
        assert resp.headers["Vary"] == "Accept-Encoding"

        with open(path, "rb") as fp:
            assert resp.body == fp.read()


class TestDirectives:

    def test_whitenoise_serve_static_unsupported_kwarg(self):
        with pytest.raises(TypeError):
            static.whitenoise_serve_static(pretend.stub(), lol_fake=True)

    def test_whitenoise_serve_static(self, monkeypatch):
        whitenoise_obj = pretend.stub()
        whitenoise_cls = pretend.call_recorder(lambda *a, **kw: whitenoise_obj)
        whitenoise_cls.config_attrs = ["autorefresh"]
        monkeypatch.setattr(static, "WhiteNoise", whitenoise_cls)

        config = pretend.stub(
            action=pretend.call_recorder(lambda d, f: None),
            registry=pretend.stub(),
        )

        static.whitenoise_serve_static(config, autorefresh=True)

        assert config.action.calls == [
            pretend.call(("whitenoise", "create instance"), mock.ANY),
        ]

        config.action.calls[0].args[1]()

        assert whitenoise_cls.calls == [pretend.call(None, autorefresh=True)]
        assert config.registry.whitenoise is whitenoise_obj

    def test_whitenoise_add_files(self):
        config = pretend.stub(
            action=pretend.call_recorder(lambda d, f: None),
            registry=pretend.stub(
                whitenoise=pretend.stub(
                    add_files=pretend.call_recorder(lambda path, prefix: None),
                ),
            ),
        )

        static.whitenoise_add_files(config, "/static/foo/", "/lol/")

        assert config.action.calls == [
            pretend.call(
                ("whitenoise", "add files", "/static/foo/", "/lol/"),
                mock.ANY,
            ),
        ]

        config.action.calls[0].args[1]()

        assert config.registry.whitenoise.add_files.calls == [
            pretend.call("/static/foo", prefix="/lol/"),
        ]


def test_includeme():
    config = pretend.stub(
        add_directive=pretend.call_recorder(lambda name, callable: None),
        add_tween=pretend.call_recorder(lambda tween, over, under: None),
    )

    static.includeme(config)

    assert config.add_directive.calls == [
        pretend.call(
            "whitenoise_serve_static",
            static.whitenoise_serve_static,
        ),
        pretend.call(
            "whitenoise_add_files",
            static.whitenoise_add_files,
        ),
    ]
    assert config.add_tween.calls == [
        pretend.call(
            "warehouse.static.whitenoise_tween_factory",
            over=[
                "warehouse.utils.compression.compression_tween_factory",
                EXCVIEW,
            ],
            under=[
                "warehouse.csp.content_security_policy_tween_factory",
                "warehouse.config.require_https_tween_factory",
                INGRESS,
            ],
        ),
    ]
