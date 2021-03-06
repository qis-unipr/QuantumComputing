# Copyright 2018, Davide Ferrari and Michele Amoretti
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

APItoken = None

URL = 'https://quantumexperience.ng.bluemix.net/api'

if 'APItoken' not in locals():
    raise Exception("Please set up your api access token. See config.py.")
