Contributing
============

If you find issues, `report them on GitHub <https://github.com/alexdlaird/ha-hearth/issues>`_.

If you would like to contribute to the code, the process is pretty simple:

1. Familiarise yourself with this integration, `Hearth's home API <https://www.meethearth.app/support.html#hearth-api>`_, and `Home Assistant's developer documentation <https://developers.home-assistant.io/>`_.
2. Fork `the repository on GitHub <https://github.com/alexdlaird/ha-hearth>`_ and start implementing changes.
3. Write a test that plainly validates the changes made.
4. Build and test locally with ``make test``, which tests against the current Home Assistant and needs Python 3.14
   (``make test PYTHON_BIN=python3.14`` if that isn't your default ``python``). To test against an older Home Assistant,
   pass the ``pytest-homeassistant-custom-component`` release that pins it, e.g.
   ``make test HA_TEST_HARNESS=0.13.298`` for 2025.12.0 on Python 3.13 (this also pins ``pycares<5``, which those
   releases need).
5. Ensure no linting errors were introduced by running ``make check``.
6. Submit a `pull requests <https://help.github.com/en/articles/creating-a-pull-request-from-a-fork>`_ to get the changes merged.

Also be sure to review the `Code of Conduct <https://github.com/alexdlaird/ha-hearth?tab=coc-ov-file#contributor-covenant-code-of-conduct>`_ before
submitting issues or pull requests.

Want to contribute financially? If you've found ``ha-hearth`` useful, `sponsorship <https://github.com/sponsors/alexdlaird>`_
would also be greatly appreciated!
