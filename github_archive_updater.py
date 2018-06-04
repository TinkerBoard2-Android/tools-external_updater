# Copyright (C) 2018 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""Module to update packages from GitHub archive."""


import json
import re
import shutil
import urllib.request

import archive_utils
import fileutils
import metadata_pb2    # pylint: disable=import-error
import updater_utils

GITHUB_URL_PATTERN = (r'^https:\/\/github.com\/([-\w]+)\/([-\w]+)\/' +
                      r'(releases\/download\/|archive\/)')
GITHUB_URL_RE = re.compile(GITHUB_URL_PATTERN)


class GithubArchiveUpdater():
    """Updater for archives from GitHub.

    This updater supports release archives in GitHub. Version is determined by
    release name in GitHub.
    """

    VERSION_FIELD = 'tag_name'

    def __init__(self, url, proj_path, metadata):
        self.proj_path = proj_path
        self.metadata = metadata
        self.old_url = url
        self.owner = None
        self.repo = None
        self.data = None
        self._parse_url(url)

    def _parse_url(self, url):
        if url.type != metadata_pb2.URL.ARCHIVE:
            raise ValueError('Only archive url from Github is supported.')
        match = GITHUB_URL_RE.match(url.value)
        if match is None:
            raise ValueError('Url format is not supported.')
        try:
            self.owner, self.repo = match.group(1, 2)
        except IndexError:
            raise ValueError('Url format is not supported.')

    def get_latest_version(self):
        """Checks upstream and returns the latest version name we found."""

        url = 'https://api.github.com/repos/{}/{}/releases/latest'.format(
            self.owner, self.repo)
        with urllib.request.urlopen(url) as request:
            self.data = json.loads(request.read().decode())
        return self.data[self.VERSION_FIELD]

    def get_current_version(self):
        """Returns the latest version name recorded in METADATA."""
        return self.metadata.third_party.version

    def _write_metadata(self, url, path):
        updated_metadata = metadata_pb2.MetaData()
        updated_metadata.CopyFrom(self.metadata)
        updated_metadata.third_party.version = self.data[self.VERSION_FIELD]
        for metadata_url in updated_metadata.third_party.url:
            if metadata_url == self.old_url:
                metadata_url.value = url
        fileutils.write_metadata(path, updated_metadata)

    def update(self):
        """Updates the package.

        Has to call get_latest_version() before this function.
        """

        supported_assets = [
            a for a in self.data['assets']
            if archive_utils.is_supported_archive(a['browser_download_url'])]

        # Finds the minimum sized archive to download.
        minimum_asset = min(
            supported_assets, key=lambda asset: asset['size'], default=None)
        if minimum_asset is not None:
            latest_url = minimum_asset.get('browser_download_url')
        else:
            # Guess the tarball url for source code.
            latest_url = 'https://github.com/{}/{}/archive/{}.tar.gz'.format(
                self.owner, self.repo, self.data.get('tag_name'))

        temporary_dir = None
        try:
            temporary_dir = archive_utils.download_and_extract(latest_url)
            package_dir = archive_utils.find_archive_root(temporary_dir)
            self._write_metadata(latest_url, package_dir)
            updater_utils.replace_package(package_dir, self.proj_path)
        finally:
            shutil.rmtree(temporary_dir, ignore_errors=True)
            urllib.request.urlcleanup()
