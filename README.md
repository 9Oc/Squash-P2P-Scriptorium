This is a collection of 1-file python/batch scripts for making life easier when creating P2P releases.

# Subtitle Scripts

## suppf
suppf is PGS subtitle palette fixer that corrects common subtitle color issues.

Requirements: Python 3.09+

Dependencies: None

### Usage
Supplying only an input and output defaults to using automatic detection for what color(s) to fix.

`suppf.py input.sup output.sup`

Supplying a main color signals to the script that this is the color meant to be fixed.

`suppf.py input.sup output.sup --main-color yellow`

`suppf.py input.sup output.sup --main-color blue`

`suppf.py input.sup output.sup --main-color a7a792`

Appending the quiet argument suppresses verbose output.

`append --quiet for no debug output`


### Examples
Input .sup

![Bad colors that need to be fixed](https://img.onlyimage.org/8qfPAc.png)

Fixed .sup with suppf

![Fixed](https://img.onlyimage.org/8qfLnZ.png)
