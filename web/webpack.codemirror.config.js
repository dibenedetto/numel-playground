// webpack.codemirror.config.js
const path = require('path');

module.exports = {
  mode: 'production',
  entry: './src/codemirror-bundle.js',
  output: {
    path: path.resolve(__dirname, 'dist'),
    filename: 'codemirror-bundle.js',
    library: {
      name: 'CodeEditor',
      type: 'window',
    },
  },
  resolve: {
    extensions: ['.js', '.ts', '.json'],
  },
  devtool: 'source-map',
  optimization: {
    minimize: true,
    usedExports: true,
  }
};
