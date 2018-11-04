# chooser

Super simple chooser of backgrounds. Used as a random background roulette for [my poetry blog](benjspriggs.tumblr.com).

## Setup

Requires a `.settings` file:
```json
{"config": 
	{
		"app-root": "<root dir of this app>/", 
		"root": "<web root (external)>/", 
		"urls-path": "<path to where possible images are stored>.txt",
		"api-key": "<key to TinyPNG api>",
		"cache-prefix": "<hostname to prefix cached images with>/"
	}
}
```
