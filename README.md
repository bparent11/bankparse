# bankparse
**bankparse** is a Python package designed to simplify the extraction of your **own** bank data. Indeed in France, it's common that your bank doesn't give you clear analysis on what you spend if you don't subscribe to it. You only receive a pdf file of all your expenses and income of the month. That's why bankparse is here, to simplify the extraction of your data from those pdf files. You can get your data as JSON format or pandas DataFrame with 3 lines of code.

## Table of Contents

- [Vision of the project](#vision)
- [Features](#features)
- [Installation](#installation)
- [Examples](#examples)

## Vision
As develop in the introduction, the project aims to give back people their own data in an easy way. At this moment, the package will mainly cover the French market.

## Features

### _bankparse.file_manager module_
This module is designed to manage all kind of files provided by the banks.
It helps you to get the owner and the extract date of the file, in addition to
retrieve your account's data (label, ID, ...).

The available banks are : Crédit Agricole, Crédit Mutuel, Bourso Bank.

[See more about available features](https://github.com/bparent11/bankparse/tree/main/src/bankparse/file_manager)

### _bankparse.table_manager module_
This module is designed to manage all kind of tables within the statement files provided by the banks.
It helps you to act on the data, retrieve transactions and balance statements.
Different kind of table do exist, but I don't have access to all of these yet, that's why what you're looking for could not be available at this moment.

The available banks are : Crédit Agricole, Crédit Mutuel, Bourso Bank.

[See more about available features](https://github.com/bparent11/bankparse/tree/main/src/bankparse/table_manager)

## Installation
Coming soon.

## Examples
Coming soon.