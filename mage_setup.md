## MAGE Local Setup Summary

MAGE is an open-source multi-agent RTL code generator; the paper states that its implementation uses Icarus Verilog as the Verilog compiler/simulator and LlamaIndex as the LLM API interface.  The current GitHub README gives the following local setup flow. ([GitHub][1])

### 1. Clone and install the Python package

```bash
git clone --recursive https://github.com/stable-lab/MAGE.git
cd MAGE

conda create -n mage python=3.11
conda activate mage

pip install .
```

The project requires Python 3.11 or higher, and `pip install .` installs the package dependencies such as LlamaIndex OpenAI/Anthropic/Vertex adapters, Pydantic, Rich, and Tiktoken. ([GitHub][2])

### 2. Configure LLM API keys

You can either export keys as environment variables or create a `key.cfg` file in the MAGE directory. ([GitHub][1])

```bash
# Option A: environment variables
export OPENAI_API_KEY="..."
export ANTHROPIC_API_KEY="..."

# Option B: key.cfg
cat > key.cfg <<EOF
OPENAI_API_KEY='xxxxxxx'
ANTHROPIC_API_KEY='xxxxxxx'
VERTEX_SERVICE_ACCOUNT_PATH='xxxxxxx'
VERTEX_REGION='xxxxxxx'
EOF
```

### 3. Install Icarus Verilog

MAGE’s README expects Icarus Verilog 12.0. ([GitHub][1])

Ubuntu source build:

```bash
sudo apt install -y autoconf gperf make gcc g++ bison flex

git clone https://github.com/steveicarus/iverilog.git
cd iverilog
git checkout v12-branch
sh ./autoconf.sh
./configure
make -j4
sudo make install

iverilog -v
```

Expected first line:

```bash
Icarus Verilog version 12.0 (stable) (v12_0)
```

macOS:

```bash
brew install icarus-verilog
iverilog -v
```

### 4. Install Verilator

```bash
# Ubuntu package install
sudo apt install verilator
```

Or build from source:

```bash
git clone https://github.com/verilator/verilator
cd verilator
autoconf
export VERILATOR_ROOT=$(pwd)
./configure
make -j4
```

The README lists both apt-based and source-build options. ([GitHub][1])

### 5. Install Pyverilog

```bash
pip3 install jinja2 ply

git clone https://github.com/PyHDI/Pyverilog.git
cd Pyverilog
python3 setup.py install --user
```

This is listed as a separate Pyverilog setup step in the README. ([GitHub][1])

### 6. Get the benchmark submodule

From the MAGE repository root:

```bash
git submodule update --init --recursive
```

The README uses the `verilog-eval` benchmark submodule. ([GitHub][1])

### 7. Run a local test

```bash
python tests/test_top_agent.py
```

Edit `args_dict` in `tests/test_top_agent.py` before running. The README example uses Anthropic Claude 3.5 Sonnet, `verilog_eval_v2`, `../verilog-eval`, temperature `0.85`, top-p `0.95`, max token `8192`, and `key.cfg` as the key config path. ([GitHub][1])

Example configuration:

```python
args_dict = {
    "provider": "anthropic",
    "model": "claude-3-5-sonnet-20241022",
    "filter_instance": "^(Prob011_norgate)$",
    "type_benchmark": "verilog_eval_v2",
    "path_benchmark": "../verilog-eval",
    "run_identifier": "local_test",
    "n": 1,
    "temperature": 0.85,
    "top_p": 0.95,
    "max_token": 8192,
    "use_golden_tb_in_mage": True,
    "key_cfg_path": "key.cfg",
}
```

### 8. Development install only

```bash
pip install -e . --config-settings editable_mode=compat
pre-commit install
```

Use this only if you plan to modify MAGE source code locally. ([GitHub][1])

[1]: https://github.com/stable-lab/MAGE-A-Multi-Agent-Engine-for-Automated-RTL-Code-Generation "GitHub - stable-lab/MAGE: MAGE: A Multi-Agent Engine for Automated RTL Code Generation · GitHub"
[2]: https://github.com/stable-lab/MAGE/blob/main/pyproject.toml "MAGE/pyproject.toml at main · stable-lab/MAGE · GitHub"
