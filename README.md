# Compiler

A Python3 compiler for the Joos 1W language.

## Running Locally

### Get `Python 3.10.12` or greater

#### Install `Python` Requirements

```bash
sudo apt install curl build-essential libssl-dev zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev curl libncursesw5-dev xz-utils tk-dev libxml2-dev libxmlsec1-dev libffi-dev liblzma-dev
```

#### Curl `pyenv` from Using `bash`

```bash
curl https://pyenv.run | bash
```

#### Update `~/.bashrc` with the Relevant Lines

```bash
printf "%s\n" '' 'export PATH="$HOME/.pyenv/bin:$PATH"' 'eval "$(pyenv init -)"' 'eval "$(pyenv virtualenv-init -)"' >> ~/.bashrc
```

#### Reload the `~/.bashrc`

```bash
source ~/.bashrc
```

#### Install `Python 3.10.12`

```bash
pyenv install 3.10.12
```

### Create a Virtual Environment

#### Use `Python 3.10.12`

```bash
pyenv local 3.10.12
```

#### Make the Virtual Environment Folder

```bash
python3 -m venv env
```

#### Activate Virtual Environment

```bash
source env/bin/activate
```

### Run the Relevant `Python` File

#### Install the Given Requirements

```bash
python3 -m pip install -r requirements.txt
```

#### Run the `main.py` File

```bash
python3 main.py -a=1
```

## Building

### Single Input file

#### Create the joosc executable for the file

``` bash
make
```

#### Parse the Input File

``` bash
./joosc ./assignment_testcases/a1/J1_01.java
```

### Multiple Input Files

#### Create the joosc executable for the files

``` bash
make
```

#### Parse the Input Files

``` bash
./joosc ./assignment_testcases/a1/J1_01.java
```
