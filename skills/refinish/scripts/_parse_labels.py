"""The labels of a parse map: seethrough_parse.py writes them and auto_parts.py --parse reads them. 0 is the background
or no sure part; See-Through's parts come from 1; then, from 20, an eye a promptable segmenter split: its iris, its
white, its lashes, or the whole eye kept as drawn."""
PARSE_PARTS = ('hair', 'headwear', 'face', 'eyes', 'eyewear', 'ears', 'earwear', 'nose', 'mouth', 'neck', 'neckwear',
               'topwear', 'handwear', 'bottomwear', 'legwear', 'footwear', 'tail', 'wings', 'objects')
EYE_PARTS = ('iris', 'eye-white', 'lashes', 'eye-kept')
PARSE = {p: k + 1 for k, p in enumerate(PARSE_PARTS + EYE_PARTS)}
EYE0 = PARSE["iris"]
