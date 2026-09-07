package main

import "github.com/kandev/kandev/pkg/pluginsdk"

type themePlugin struct {
	pluginsdk.UnimplementedPlugin
}

func main() {
	pluginsdk.Serve(&themePlugin{})
}
