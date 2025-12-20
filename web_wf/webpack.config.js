// webpack.config.js
const path = require('path');
const webpack = require('webpack');

module.exports = {
  mode: 'production', // or 'development' for debugging
  entry: './src/agui-bundle.js',
  output: {
    path: path.resolve(__dirname, 'dist'),
    filename: 'agui-client.bundle.js',
    library: {
      name: 'AGUI',
      type: 'window', // Makes it available as window.AGUI
    },
  },
  resolve: {
    extensions: ['.js', '.ts', '.json'],
    fallback: {
      // Add Node.js polyfills if needed
      "buffer": require.resolve("buffer"),
      "stream": require.resolve("stream-browserify"),
      "util": require.resolve("util"),
      "url": require.resolve("url"),
      "querystring": require.resolve("querystring-es3"),
    }
  },
  module: {
    rules: [
      {
        test: /\.(js|ts)$/,
        exclude: /node_modules/,
        use: {
          loader: 'babel-loader',
          options: {
            presets: [
              ['@babel/preset-env', {
                targets: {
                  browsers: ['> 1%', 'last 2 versions']
                }
              }]
            ]
          }
        }
      }
    ]
  },
  plugins: [
    new webpack.ProvidePlugin({
      Buffer: ['buffer', 'Buffer'],
    }),
  ],
  devtool: 'source-map', // Generate source maps for debugging
  optimization: {
    minimize: true,
    usedExports: true,
  }
};