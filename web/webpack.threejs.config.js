// webpack.threejs.config.js
const path = require('path');

module.exports = {
  mode: 'production',
  entry: './src/threejs-bundle.js',
  output: {
    path: path.resolve(__dirname, 'dist'),
    filename: 'threejs-bundle.js',
    library: {
      name: 'ThreeViewer',
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
