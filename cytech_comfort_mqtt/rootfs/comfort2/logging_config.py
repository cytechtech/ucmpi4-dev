# Copyright (c) 2018 Khor Chin Heong (koochyrat@gmail.com)
# Copyright (c) 2025 Ingo de Jager (ingodejager@gmail.com)
# Copyright (c) 2026 Cytech Technology Pte Ltd
#
# Original project code by Khor Chin Heong.
# Modifications in 2025 by Ingo de Jager.
# Further modifications and enhancements in 2026 by Cytech Technology Pte Ltd.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#        http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import logging
import os
from logging.handlers import RotatingFileHandler

RAM_LOG_FILE = "/dev/shm/cytech_comfort_mqtt.log"

def setup_ram_logging(level=logging.INFO):
    # Keep bridge diagnostics in RAM; stdout may be persisted by the host.
    root = logging.getLogger()

    root.setLevel(level)

    formatter = logging.Formatter(
        '%(asctime)s %(levelname)-8s [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    file_handler = next((handler for handler in root.handlers
                         if isinstance(handler, RotatingFileHandler)
                         and handler.baseFilename == os.path.abspath(RAM_LOG_FILE)), None)
    if file_handler is None:
        file_handler = RotatingFileHandler(
            RAM_LOG_FILE, maxBytes=1024 * 1024, backupCount=2, encoding="utf-8"
        )
        root.addHandler(file_handler)

    file_handler.setLevel(level)
    file_handler.setFormatter(formatter)
